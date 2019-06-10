import logging
from .. import repositories, utilities, PlatformException
import attr

logger = logging.getLogger('dataloop.item')


@attr.s
class Item:
    """
    Item object
    """
    # platform
    client_api = attr.ib()
    id = attr.ib()
    annotations_link = attr.ib()
    stream = attr.ib()
    thumbnail = attr.ib()
    metadata = attr.ib()
    url = attr.ib()
    system = attr.ib()

    # params
    annotated = attr.ib()
    filename = attr.ib()
    mimetype = attr.ib()
    name = attr.ib()
    size = attr.ib()
    type = attr.ib()

    # entities
    dataset = attr.ib()

    # repositories
    _annotations = attr.ib()

    # defaults
    width = attr.ib()
    height = attr.ib()

    @classmethod
    def from_json(cls, _json, dataset, client_api):
        """
        Build an item entity object from a json

        :param _json: _json respons form host
        :param dataset: dataset in which the annotation's item is located
        :param item: annotation's item
        :param client_api: client_api
        :return: Item object
        """
        if _json['type'] == 'dir':
            return cls(
                client_api=client_api,
                dataset=dataset,
                annotated=None,
                annotations_link=None,
                stream=None,
                thumbnail=None,
                url=_json['url'],
                filename=_json['filename'],
                id=_json['id'],
                metadata=_json['metadata'],
                mimetype=None,
                name=_json['name'],
                size=None,
                system=None,
                type=_json['type'])
        elif _json['type'] == 'file':
            return cls(
                client_api=client_api,
                dataset=dataset,
                annotated=_json['annotated'],
                annotations_link=_json['annotations'],
                stream=_json['stream'],
                thumbnail=_json['thumbnail'],
                url=_json['url'],
                filename=_json['filename'],
                id=_json['id'],
                metadata=_json['metadata'],
                mimetype=_json['metadata']['system']['mimetype'],
                name=_json['name'],
                size=_json['metadata']['system']['size'],
                system=_json['metadata']['system'],
                type=_json['type'])
        else:
            message = 'Unknown item type: %s' % _json['type']
            raise PlatformException('404', message)

    @_annotations.default
    def set_annotations(self):
        return repositories.Annotations(dataset=self.dataset, item=self, client_api=self.client_api)

    @property
    def annotations(self):
        assert isinstance(self._annotations, repositories.Annotations)
        return self._annotations

    @height.default
    def set_height(self):
        height = None
        if self.system is not None and 'height' in self.system:
            height = self.system['height']
        return height

    @width.default
    def set_width(self):
        width = None
        if self.system is not None and 'width' in self.system:
            width = self.system['width']
        return width

    def set_metadata(self, metadata):
        self.metadata = metadata

    def to_json(self):
        """
        Returns platform _json format of object

        :return: platform json format of object
        """
        if self.type == 'dir':
            _json = attr.asdict(self,
                                filter=attr.filters.include(attr.fields(Item).id,
                                                            attr.fields(Item).filename,
                                                            attr.fields(Item).type,
                                                            attr.fields(Item).metadata,
                                                            attr.fields(Item).name,
                                                            attr.fields(Item).url))
        elif self.type == 'file':
            _json = attr.asdict(self,
                                filter=attr.filters.include(attr.fields(Item).id,
                                                            attr.fields(Item).filename,
                                                            attr.fields(Item).type,
                                                            attr.fields(Item).metadata,
                                                            attr.fields(Item).name,
                                                            attr.fields(Item).url,
                                                            attr.fields(Item).annotated,
                                                            attr.fields(Item).thumbnail,
                                                            attr.fields(Item).stream))
            _json.update({'annotations': self.annotations_link})
        else:
            message = 'Unknown item type: %s' % self.type
            raise PlatformException('404', message)
        return _json

    def from_dict(self, metadata):
        # does nothing
        return

    def print(self):
        utilities.List([self]).print()

    def download(self, save_locally=True, local_path=None,
                 chunk_size=8192, download_options=None,
                 download_item=True, annotation_options=None,
                 verbose=True, show_progress=False):
        """
        Get item's binary data
        Calling this method will returns the item body itself , an image for example with the proper mimetype.
        
        :param save_locally: bool. save to file or return buffer
        :param local_path: local folder or filename to save to. if folder ends with * images with be downloaded directly
         to folder. else - an "images" folder will be create for the images
        :param chunk_size:
        :param verbose:
        :param show_progress:
        :param download_options: {'overwrite': True/False, 'relative_path': True/False}
        :param download_item:
        :param annotation_options: download annotations options: ['mask', 'img_mask', 'instance', 'json']
        :return: 
        """
        return self.dataset.items.download(item_id=self.id,
                                           save_locally=save_locally, local_path=local_path,
                                           chunk_size=chunk_size, download_options=download_options,
                                           download_item=download_item, annotation_options=annotation_options,
                                           verbose=verbose, show_progress=show_progress)

    def delete(self):
        """
        Delete item from platform

        :return: True
        """
        return self.dataset.items.delete(item_id=self.id)

    def update(self, system_metadata=False):
        """
        Update items metadata

        :param system_metadata: bool
        :return: Item object
        """
        return self.dataset.items.update(item=self, system_metadata=system_metadata)
