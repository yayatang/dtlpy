import behave
import os
import glob
import shutil


@behave.when(u'I download dataset to "{local_path}"')
def step_impl(context, local_path):
    local_path = os.path.join(os.environ['DATALOOP_TEST_ASSETS'], local_path)

    context.project.datasets.download(dataset_name=context.dataset.name,
                                      dataset_id=context.dataset.id,
                                      query=None,
                                      local_path=local_path,
                                      filetypes=None,
                                      num_workers=None,
                                      download_options=None,
                                      save_locally=True,
                                      download_item=True,
                                      annotation_options=['mask', 'img_mask', 'instance', 'json'],
                                      opacity=1,
                                      with_text=False,
                                      thickness=3)


@behave.then(u'There is no "{log}" file in folder "{download_path}"')
def step_impl(context, log, download_path):
    download_path = os.path.join(os.environ['DATALOOP_TEST_ASSETS'], download_path)

    files = os.listdir(download_path)
    for file in files:
        assert log not in file


@behave.then(u'Dataset downloaded to "{download_path}" is equal to dataset in "{should_be_path}"')
def step_impl(context, download_path, should_be_path):
    download_path = os.path.join(os.environ['DATALOOP_TEST_ASSETS'], download_path)
    should_be_path = os.path.join(os.environ['DATALOOP_TEST_ASSETS'], should_be_path)
    files = os.listdir(download_path)
    excepted_dirs = ['image', 'img_mask', 'instance', 'json', 'mask']
    for file in excepted_dirs:
        assert file in files


@behave.given(u'There are no folder or files in folder "{dir_path}"')
def step_impl(context, dir_path):
    dir_path = os.path.join(os.environ['DATALOOP_TEST_ASSETS'], dir_path)
    dir_path = dir_path + "/*"

    files = glob.glob(dir_path)
    for f in files:
        if os.path.isdir(f):
            shutil.rmtree(f)
        elif os.path.isfile(f):
            os.remove(f)

    assert len(glob.glob(dir_path)) == 0
