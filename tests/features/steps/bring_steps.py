import os
# set var for assets
os.environ['DATALOOP_TEST_ASSETS'] = os.path.join(os.getcwd(), 'tests', 'assets')

# os.environ['DATALOOP_TEST_ASSETS'] = '/Users/aharonlouzon/Desktop/Dataloop/SDK/dtlpy/tests/assets'
# os.chdir('/Users/aharonlouzon/Desktop/Dataloop/SDK/dtlpy')

from tests.features.steps.projects_repo import test_projects_create
from tests.features.steps.projects_repo import test_projects_list
from tests.features.steps.projects_repo import test_projects_get
from tests.features.steps.projects_repo import test_projects_delete

from tests.features.steps.project_entity import test_project_repo_methods

from tests.features.steps.datasets_repo import test_datasets_create
from tests.features.steps.datasets_repo import test_datasets_list
from tests.features.steps.datasets_repo import test_datasets_get
from tests.features.steps.datasets_repo import test_datasets_delete
from tests.features.steps.datasets_repo import test_datasets_update
from tests.features.steps.datasets_repo import test_datasets_download_annotations
from tests.features.steps.datasets_repo import test_datasets_download

from tests.features.steps.dataset_entity import test_dataset_repo_methods

from tests.features.steps.annotations_repo import test_annotations_get
from tests.features.steps.annotations_repo import test_annotations_list
from tests.features.steps.annotations_repo import test_annotations_delete
from tests.features.steps.annotations_repo import test_annotations_download
from tests.features.steps.annotations_repo import test_annotations_update
from tests.features.steps.annotations_repo import test_annotations_upload
from tests.features.steps.annotations_repo import test_annotations_to_mask

from tests.features.steps.annotation_entity import test_annotation_repo_methods

from tests.features.steps.items_repo import test_items_get
from tests.features.steps.items_repo import test_items_upload
from tests.features.steps.items_repo import test_items_list
from tests.features.steps.items_repo import test_items_update
from tests.features.steps.items_repo import test_items_set_items_entity
from tests.features.steps.items_repo import test_items_get_all_items
from tests.features.steps.items_repo import test_items_download_batch
from tests.features.steps.items_repo import test_items_upload_batch
from tests.features.steps.items_repo import test_items_delete
from tests.features.steps.items_repo import test_items_download


from tests.features.steps.item_entity import test_item_repo_methods

from tests.features.steps.ontologies_repo import test_ontologies_create
from tests.features.steps.ontologies_repo import test_ontologies_get
from tests.features.steps.ontologies_repo import test_ontologies_delete
from tests.features.steps.ontologies_repo import test_ontologies_update

from tests.features.steps.ontology_entity import test_ontology_repo_methods

from tests.features.steps.recipes_repo import test_recipes_create
from tests.features.steps.recipes_repo import test_recipes_update
from tests.features.steps.recipes_repo import test_recipes_delete

from tests.features.steps.packages_repo import test_packages_pack
from tests.features.steps.packages_repo import test_packages_init
from tests.features.steps.packages_repo import test_packages_unpack
from tests.features.steps.packages_repo import test_packages_get
from tests.features.steps.packages_repo import test_packages_list_versions
from tests.features.steps.packages_repo import test_packages_list

from tests.features.steps.package_entity import test_package_repo_methods

from tests.features.steps.utilities import platform_interface_steps
