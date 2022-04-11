from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image
import collections.abc
import numpy as np
import collections
import logging
import shutil
import json
import copy
import tqdm
import os
import re
from ... import entities

logger = logging.getLogger('dtlpy')


class DataItem(dict):
    def __init__(self, *args, **kwargs):
        super(DataItem, self).__init__(*args, **kwargs)

    @property
    def image_filepath(self):
        return self['image_filepath']

    @image_filepath.setter
    def image_filepath(self, val):
        self['image_filepath'] = val


class DatasetGenerator:
    IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'bmp']

    def __init__(self,
                 dataset_entity: entities.Dataset,
                 annotation_type: entities.AnnotationType,
                 filters: entities.Filters = None,
                 data_path=None,
                 overwrite=False,
                 id_to_label_map=None,
                 transforms=None,
                 transforms_callback=None,
                 num_workers=0,
                 batch_size=None,
                 collate_fn=None,
                 shuffle=True,
                 seed=None,
                 to_categorical=False,
                 class_balancing=False,
                 # debug flags
                 return_originals=False,
                 ignore_empty=True
                 ) -> None:
        """
        Base Dataset Generator to build and iterate over images and annotations

        :param dataset_entity: dl.Dataset entity
        :param annotation_type: dl.AnnotationType - type of annotation to load from the annotated dataset
        :param filters: dl.Filters - filtering entity to filter the dataset items
        :param data_path: Path to Dataloop annotations (root to "item" and "json").
        :param overwrite:
        :param id_to_label_map: dict - {id: label_string} dictionary
        :param transforms: Optional transform to be applied on a sample. list, imgaug.Sequence or torchvision.transforms.Compose
        :param transforms_callback: Optional function to handle the callback of each batch.
        look at default_transforms_callback for more information. available: imgaug_transforms_callback, torchvision_transforms_callback
        :param num_workers: Optional - number of separate threads to load the images
        :param batch_size: (int, optional): how many samples per batch to load, if not none - items will always be a list
        :param collate_fn: Optional - merges a list of samples to form a mini-batch of Tensor(s).
        :param shuffle: Whether to shuffle the data (default: True) If set to False, sorts the data in alphanumeric order.
        :param seed: Optional random seed for shuffling and transformations.
        :param to_categorical: convert label id to categorical format
        :param class_balancing: if True - performing random over-sample with class ids as the target to balance training data
        :param return_originals: bool - If True, return ALSO images and annotations before transformations (for debug)
        :param ignore_empty: bool - If True, generator will NOT collect items without annotations
        """

        self._dataset_entity = dataset_entity
        if id_to_label_map is None:
            label_to_id_map = dataset_entity.instance_map
            id_to_label_map = {v: k for k, v in label_to_id_map.items()}
        else:
            # id_to_label_map is not None
            label_to_id_map = {v: k for k, v in id_to_label_map.items()}
            dataset_entity._get_ontology().instance_map = label_to_id_map
        self.id_to_label_map = id_to_label_map
        self.label_to_id_map = label_to_id_map

        if data_path is None:
            data_path = os.path.join(os.path.expanduser('~'),
                                     '.dataloop',
                                     'datasets',
                                     "{}_{}".format(dataset_entity.name,
                                                    dataset_entity.id))
        download = False
        if os.path.isdir(data_path):
            if overwrite:
                logger.warning('overwrite flag is True! deleting and overwriting')
                shutil.rmtree(data_path)
                download = True
        else:
            download = True
        if download:
            annotation_options = [entities.ViewAnnotationOptions.JSON]
            if annotation_type in [entities.AnnotationType.SEGMENTATION]:
                annotation_options.append(entities.ViewAnnotationOptions.INSTANCE)
            _ = dataset_entity.items.download(filters=filters,
                                              local_path=data_path,
                                              annotation_options=annotation_options)
        self.root_dir = data_path
        self._items_path = Path(self.root_dir).joinpath('items')
        self._json_path = Path(self.root_dir).joinpath('json')
        self._mask_path = Path(self.root_dir).joinpath('instance')
        self._transforms = transforms
        self._transforms_callback = transforms_callback
        if self._transforms is not None and self._transforms_callback is None:
            # use default callback
            self._transforms_callback = default_transforms_callback

        self.annotation_type = annotation_type
        self.num_workers = num_workers
        self.to_categorical = to_categorical
        self.num_classes = len(label_to_id_map)
        self.shuffle = shuffle
        self.seed = seed
        self.batch_size = batch_size
        self.collate_fn = collate_fn
        self.class_balancing = class_balancing
        # inits
        self.data_items = list()
        # flags
        self.return_originals = return_originals
        self.ignore_empty = ignore_empty

        ####################
        # Load annotations #
        ####################
        self.load_annotations()

    @property
    def dataset_entity(self):
        assert isinstance(self._dataset_entity, entities.Dataset)
        return self._dataset_entity

    @dataset_entity.setter
    def dataset_entity(self, val):
        assert isinstance(val, entities.Dataset)
        self._dataset_entity = val

    @property
    def n_items(self):
        return len(self.data_items)

    def _load_single(self, image_filepath, pbar=None):
        try:
            is_empty = False
            item_info = DataItem()
            # add image path
            item_info.image_filepath = str(image_filepath)
            if os.stat(image_filepath).st_size < 5:
                logger.exception('Corrupted Image: {!r}'.format(image_filepath))
                return None, True
            # get "platform" path
            rel_path = image_filepath.relative_to(self._items_path)
            # replace suffix to JSON
            rel_path_wo_png_ext = rel_path.with_suffix('.json')
            # create local path
            annotation_filepath = Path(self._json_path, rel_path_wo_png_ext)

            if os.path.isfile(annotation_filepath):
                with open(annotation_filepath, 'r') as f:
                    data = json.load(f)
                    if 'id' in data:
                        item_id = data.get('id')
                    elif '_id' in data:
                        item_id = data.get('_id')
                    annotations = entities.AnnotationCollection.from_json(data)
            else:
                item_id = ''
                annotations = None
            item_info.update(item_id=item_id)
            if self.annotation_type is not None:
                # add item id from json
                box_coordinates = list()
                classes_ids = list()
                labels = list()
                if annotations is not None:
                    for annotation in annotations:
                        if 'user' in annotation.metadata and \
                                'model' in annotation.metadata['user']:
                            # and 'name' in annotation.metadata['user']['model']:
                            # Do not use prediction annotations in the data generator
                            continue
                        if annotation.type == self.annotation_type:
                            if annotation.label not in self.label_to_id_map:
                                logger.warning(
                                    'Missing label {!r} in label_to_id_map. Skipping.. Use label_to_id_map for other behaviour'.format(annotation.label))
                            else:
                                classes_ids.append(self.label_to_id_map[annotation.label])
                            labels.append(annotation.label)
                            box_coordinates.append(np.asarray([annotation.left,
                                                               annotation.top,
                                                               annotation.right,
                                                               annotation.bottom]))

                            if annotation.type not in [entities.AnnotationType.CLASSIFICATION,
                                                       entities.AnnotationType.SEGMENTATION,
                                                       entities.AnnotationType.BOX]:
                                raise ValueError('unsupported annotation type: {}'.format(annotation.type))
                # reorder for output
                item_info.update({entities.AnnotationType.BOX.value: np.asarray(box_coordinates).astype(float),
                                  entities.AnnotationType.CLASSIFICATION.value: np.asarray(classes_ids),
                                  'labels': labels})
                if len(item_info['labels']) == 0:
                    logger.debug('Empty annotation for image filename: {}'.format(image_filepath))
                    is_empty = True
            if self.annotation_type in [entities.AnnotationType.SEGMENTATION]:
                # get "platform" path
                rel_path = image_filepath.relative_to(self._items_path)
                # replace suffix to PNG
                rel_path_wo_png_ext = rel_path.with_suffix('.png')
                # create local path
                mask_filepath = Path(self._mask_path, rel_path_wo_png_ext)
                if not os.path.isfile(mask_filepath):
                    logger.debug('Empty annotation for image filename: {}'.format(image_filepath))
                    is_empty = True
                item_info.update({entities.AnnotationType.SEGMENTATION.value: str(mask_filepath)})
            item_info.update(annotation_filepath=str(annotation_filepath))
            return item_info, is_empty
        except Exception:
            logger.exception('failed loading item in generator! {!r}'.format(image_filepath))
            return None, True
        finally:
            if pbar is not None:
                pbar.update()

    def load_annotations(self):
        logger.info(f"Collecting items with the following extensions: {self.IMAGE_EXTENSIONS}")
        files = list()
        for ext in self.IMAGE_EXTENSIONS:
            # build regex to ignore extension case
            regex = '*.{}'.format(''.join(['[{}{}]'.format(letter.lower(), letter.upper()) for letter in ext]))
            files.extend(self._items_path.rglob(regex))

        pool = ThreadPoolExecutor(max_workers=32)
        jobs = list()
        pbar = tqdm.tqdm(total=len(files), desc='Loading Data Generator')
        for image_filepath in files:
            jobs.append(pool.submit(self._load_single,
                                    image_filepath=image_filepath,
                                    pbar=pbar))
        outputs = [job.result() for job in jobs]
        pbar.close()

        n_items = len(outputs)
        n_empty_items = sum([1 for _, is_empty in outputs if is_empty is True])

        output_msg = 'Done loading items. Total items loaded: {}.'.format(n_items)
        if n_empty_items > 0:
            output_msg += '{action} {n_empty_items} items without annotations'.format(
                action='IGNORING' if self.ignore_empty else 'INCLUDING',
                n_empty_items=n_empty_items)

        if self.ignore_empty:
            # take ONLY non-empty
            data_items = [data_item for data_item, is_empty in outputs if is_empty is False]
        else:
            # take all
            data_items = [data_item for data_item, is_empty in outputs]

        self.data_items = data_items
        if len(self.data_items) == 0:
            logger.warning(output_msg)
        else:
            logger.info(output_msg)
        ###################
        # class balancing #
        ###################
        labels = [label for item in self.data_items for label in item.get('labels', list())]
        logger.info(f"Data Generator labels balance statistics: {collections.Counter(labels)}")
        if self.class_balancing:
            try:
                from imblearn.over_sampling import RandomOverSampler
            except Exception:
                logger.error(
                    'Class balancing is ON but missing "imbalanced-learn". run "pip install -U imbalanced-learn" and try again')
                raise
            logger.info('Class balance is on!')
            class_ids = [class_id for item in self.data_items for class_id in item['class']]
            dummy_inds = [i_item for i_item, item in enumerate(self.data_items) for _ in item['class']]
            over_sampler = RandomOverSampler(random_state=42)
            X_res, y_res = over_sampler.fit_resample(np.asarray(dummy_inds).reshape(-1, 1), np.asarray(class_ids))
            over_sampled_data_items = [self.data_items[i] for i in X_res.flatten()]
            oversampled_labels = [label for item in over_sampled_data_items for label in item['labels']]
            logger.info(f"Data Generator labels after oversampling: {collections.Counter(oversampled_labels)}")
            self.data_items = over_sampled_data_items

        if self.shuffle:
            if self.seed is None:
                self.seed = 256
            np.random.seed(self.seed)
            np.random.shuffle(self.data_items)

    def transform(self, image, target=None):
        if self._transforms is not None:
            image, target = self._transforms_callback(transforms=self._transforms,
                                                      image=image,
                                                      target=target,
                                                      annotation_type=self.annotation_type)
        return image, target

    def _to_dtlpy(self, targets, labels=None):
        annotations = entities.AnnotationCollection(item=None)
        annotations._dataset = self._dataset_entity
        if labels is None:
            labels = [None] * len(targets)
        if self.annotation_type == entities.AnnotationType.SEGMENTATION:
            for label, label_ind in self.label_to_id_map.items():
                target = targets == label_ind
                if np.any(target):
                    annotations.add(annotation_definition=entities.Segmentation(geo=target,
                                                                                label=label))
        elif self.annotation_type == entities.AnnotationType.BOX:
            for target, label in zip(targets, labels):
                annotations.add(annotation_definition=entities.Box(left=target[0],
                                                                   top=target[1],
                                                                   right=target[2],
                                                                   bottom=target[3],
                                                                   label=label))
        elif self.annotation_type == entities.AnnotationType.CLASSIFICATION:
            for target, label in zip(targets, labels):
                annotations.add(annotation_definition=entities.Classification(label=label))
        else:
            raise ValueError('unsupported annotation type: {}'.format(self.annotation_type))
        # set dataset for color
        for annotation in annotations:
            annotation._dataset = self._dataset_entity
        return annotations

    def visualize(self, idx=None, return_output=False, plot=True):
        import matplotlib.pyplot as plt
        if idx is None:
            idx = np.random.randint(self.__len__())
        if self.batch_size is not None:
            raise ValueError('can visualize only of batch_size in None')
        data_item = self.__getitem__(idx)
        image = Image.fromarray(data_item.get('image'))
        labels = data_item.get('labels')
        targets = data_item.get('annotations')
        annotations = self._to_dtlpy(targets=targets, labels=labels)
        mask = Image.fromarray(annotations.show(height=image.size[1],
                                                width=image.size[0],
                                                alpha=0.8))
        image.paste(mask, (0, 0), mask)
        marked_image = np.asarray(image)
        if plot:
            plt.figure()
            plt.imshow(marked_image)
        if return_output:
            return marked_image, annotations

    def __getsingleitem__(self, idx):
        data_item = copy.deepcopy(self.data_items[idx])

        image_filename = data_item.get('image_filepath')
        image = np.asarray(Image.open(image_filename))
        data_item.update({'image': image})

        annotations = data_item.get(self.annotation_type)
        if self.annotation_type == entities.AnnotationType.SEGMENTATION:
            # if segmentation - read from file
            mask_filepath = annotations
            annotations = np.asarray(Image.open(mask_filepath).convert('L'))
        if self.to_categorical:
            onehot = np.zeros((annotations.size, self.num_classes + 1))
            onehot[np.arange(annotations.size), annotations] = 1
            annotations = onehot
        data_item.update({'annotations': annotations})

        if self.return_originals is True:
            annotations = []
            if self.annotation_type is not None:
                annotations = data_item.get('annotations')
            data_item.update({'orig_image': image.copy(),
                              'orig_annotations': annotations.copy()})

        ###########################
        # perform transformations #
        ###########################
        if self._transforms is not None:
            annotations = data_item.get('annotations')
            image, annotations = self.transform(image, annotations)
            data_item.update({'image': image,
                              'annotations': annotations})
        return data_item

    def __iter__(self):
        """Create a generator that iterate over the Sequence."""
        for item in (self[i] for i in range(len(self))):
            yield item

    def __len__(self):
        factor = self.batch_size
        if factor is None:
            factor = 1
        return int(np.ceil(self.n_items / factor))

    def __getitem__(self, idx):
        """
            Support single index or a slice.
            Uses ThreadPoolExecutor is num_workers != 0
        """
        to_return = None
        if isinstance(idx, int):
            if self.batch_size is None:
                to_return = self.__getsingleitem__(idx)
            else:
                # if batch_size is define, convert idx to batches
                idx = slice(idx * self.batch_size, min((idx + 1) * self.batch_size, len(self.data_items)))

        if isinstance(idx, slice):
            to_return = list()
            idxs = list(range(idx.start, idx.stop,
                              idx.step if idx.step else 1))
            if self.num_workers == 0:
                for dx in idxs:
                    to_return.append(self.__getsingleitem__(dx))
            else:
                with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
                    for sample in executor.map(lambda i: self.__getsingleitem__(i), idxs):
                        to_return.append(sample)

        if to_return is None:
            raise TypeError('unsupported indexing: list indices must be integers or slices, not {}'.format(type(idx)))

        if self.collate_fn is not None:
            to_return = self.collate_fn(to_return)
        return to_return


np_str_obj_array_pattern = re.compile(r'[SaUO]')

default_collate_err_msg_format = (
    "default_collate: batch must contain tensors, numpy arrays, numbers, "
    "dicts or lists; found {}")


def default_transforms_callback(transforms, image, target, annotation_type):
    """
    Recursive call to perform the augmentations in "transforms"

    :param transforms:
    :param image:
    :param target:
    :param annotation_type:
    :return:
    """
    # get the type string without importing any other package
    transforms_type = type(transforms)

    ############
    # Handle compositions and lists of augmentations with a recursive call
    if transforms_type.__module__ == 'torchvision.transforms.transforms' and transforms_type.__name__ == 'Compose':
        # use torchvision compose
        image, target = default_transforms_callback(transforms.transforms, image, target, annotation_type)

    if transforms_type.__module__ == 'imgaug.augmenters.meta' and transforms_type.__name__ == 'Sequential':
        image, target = default_transforms_callback(list(transforms), image, target, annotation_type)

    if isinstance(transforms, list):
        for t in transforms:
            image, target = default_transforms_callback(t, image, target, annotation_type)
        return image, target

    ##############
    # Handle single annotations
    if 'imgaug.augmenters' in transforms_type.__module__:
        # handle single imgaug augmentation
        if target is not None and annotation_type is not None:
            # works for batch but running on a single image
            if annotation_type == entities.AnnotationType.BOX:
                image, target = transforms(images=[image], bounding_boxes=[target])
                target = target[0]
            elif annotation_type == entities.AnnotationType.SEGMENTATION:
                # expending to HxWx1 for the imgaug function to work
                target = target[..., None]
                image, target = transforms(images=[image], segmentation_maps=[target])
                target = target[0][:, :, 0]
            elif annotation_type == entities.AnnotationType.POLYGON:
                image, target = transforms(images=[image], polygons=[target])
                target = target[0]
            elif annotation_type == entities.AnnotationType.CLASSIFICATION:
                image = transforms(images=[image])
            else:
                raise ValueError('unsupported annotations type for image augmentations: {}'.format(annotation_type))
            image = image[0]
        else:
            image = transforms(images=[image])
            image = image[0]
    else:
        image = transforms(image)

    return image, target


def collate_default(batch):
    r"""Puts each data field into a tensor with outer dimension batch size"""
    elem = batch[0]
    elem_type = type(elem)
    if isinstance(elem, np.ndarray):
        return np.stack(batch, axis=0)
    elif elem_type.__module__ == 'numpy' and elem_type.__name__ != 'str_' and elem_type.__name__ != 'string_':
        if elem_type.__name__ == 'ndarray' or elem_type.__name__ == 'memmap':
            # array of string classes and object
            if np_str_obj_array_pattern.search(elem.dtype.str) is not None:
                raise TypeError(default_collate_err_msg_format.format(elem.dtype))
            return batch
            # return [tf.convert_to_tensor(b) for b in batch]
        elif elem.shape == ():  # scalars
            return batch
    elif isinstance(elem, float):
        return batch
    elif isinstance(elem, int):
        return batch
    elif isinstance(elem, str) or isinstance(elem, bytes) or elem is None:
        return batch
    elif isinstance(elem, collections.abc.Mapping):
        return {key: collate_default([d[key] for d in batch]) for key in elem}
    elif isinstance(elem, tuple) and hasattr(elem, '_fields'):  # namedtuple
        return elem_type(*(collate_default(samples) for samples in zip(*batch)))
    elif isinstance(elem, collections.abc.Sequence):
        transposed = zip(*batch)
        return transposed
    raise TypeError(default_collate_err_msg_format.format(elem_type))


def collate_torch(batch):
    r"""Puts each data field into a tensor with outer dimension batch size"""
    import torch
    elem = batch[0]
    elem_type = type(elem)
    if isinstance(elem, torch.Tensor):
        out = None
        if torch.utils.data.get_worker_info() is not None:
            # If we're in a background process, concatenate directly into a
            # shared memory tensor to avoid an extra copy
            numel = sum(x.numel() for x in batch)
            storage = elem.storage()._new_shared(numel)
            out = elem.new(storage)
        return torch.stack(batch, 0, out=out)
    elif elem_type.__module__ == 'numpy' and elem_type.__name__ != 'str_' and elem_type.__name__ != 'string_':
        if elem_type.__name__ == 'ndarray' or elem_type.__name__ == 'memmap':
            # array of string classes and object
            if np_str_obj_array_pattern.search(elem.dtype.str) is not None:
                raise TypeError(default_collate_err_msg_format.format(elem.dtype))
            try:
                return torch.stack([torch.as_tensor(b) for b in batch])
            except RuntimeError:
                return batch
        elif elem.shape == ():  # scalars
            return torch.as_tensor(batch)
    elif isinstance(elem, float):
        return torch.tensor(batch, dtype=torch.float64)
    elif isinstance(elem, int):
        return torch.tensor(batch)
    elif isinstance(elem, str) or isinstance(elem, bytes) or elem is None:
        return batch
    elif isinstance(elem, collections.abc.Mapping):
        return {key: collate_torch([d[key] for d in batch]) for key in elem}
    elif isinstance(elem, tuple) and hasattr(elem, '_fields'):  # namedtuple
        return elem_type(*(collate_torch(samples) for samples in zip(*batch)))
    elif isinstance(elem, collections.abc.Sequence):
        transposed = zip(*batch)
        return transposed

    raise TypeError(default_collate_err_msg_format.format(elem_type))


def collate_tf(batch):
    r"""Puts each data field into a tensor with outer dimension batch size"""
    import tensorflow as tf
    elem = batch[0]
    elem_type = type(elem)
    if isinstance(elem, tf.Tensor):
        return tf.stack(batch, axis=0)
    elif elem_type.__module__ == 'numpy' and elem_type.__name__ != 'str_' and elem_type.__name__ != 'string_':
        if elem_type.__name__ == 'ndarray' or elem_type.__name__ == 'memmap':
            # array of string classes and object
            if np_str_obj_array_pattern.search(elem.dtype.str) is not None:
                raise TypeError(default_collate_err_msg_format.format(elem.dtype))
            return tf.convert_to_tensor(batch)
            # return [tf.convert_to_tensor(b) for b in batch]
        elif elem.shape == ():  # scalars
            return tf.convert_to_tensor(batch)
    elif isinstance(elem, float):
        return tf.convert_to_tensor(batch, dtype=tf.float64)
    elif isinstance(elem, int):
        return tf.convert_to_tensor(batch)
    elif isinstance(elem, str) or isinstance(elem, bytes) or elem is None:
        return batch
    elif isinstance(elem, collections.abc.Mapping):
        return {key: collate_tf([d[key] for d in batch]) for key in elem}
    elif isinstance(elem, tuple) and hasattr(elem, '_fields'):  # namedtuple
        return elem_type(*(collate_tf(samples) for samples in zip(*batch)))
    elif isinstance(elem, collections.abc.Sequence):
        transposed = zip(*batch)
        return transposed
    raise TypeError(default_collate_err_msg_format.format(elem_type))
