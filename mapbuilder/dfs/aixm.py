import logging
from collections.abc import Iterator
from urllib import request

from mapbuilder.dfs.models import BaseItem, DFSDataset, GroupItem, LeafItem


def get_dfs_aixm_datasets() -> dict[int, dict[str, LeafItem]]:
    """Retrieves the available DFS AIXM datasets"""
    dataset_info_raw = request.urlopen("https://aip.dfs.de/datasets/rest/").read()
    available_datasets = {}
    try:
        dataset = DFSDataset.model_validate_json(dataset_info_raw)
        for amdt in dataset.amdts:
            amdt_idx = int(amdt.amdt)
            available_datasets[amdt_idx] = {}
            for ds in amdt.metadata.datasets:
                for ld in get_leaf_datasets(ds):
                    available_datasets[amdt_idx][ld.name] = ld
            logging.debug(f"Received {len(amdt.metadata.datasets)} AIXM datasets from DFS")
    except ValueError:
        logging.exception("Cannot parse DFSDataset")

    return available_datasets


def get_dfs_aixm_url(datasets: dict[str, LeafItem], amdt_id: int, dataset_name: str) -> str | None:
    """Returns the proper AIXM URL for the given datasets, amendment and dataset name"""
    if dataset_name in datasets:
        for release in datasets[dataset_name].releases:
            if release.type.startswith("AIXM"):
                return f"https://aip.dfs.de/datasets/rest/{amdt_id}/{release.filename}"

    return None


def get_leaf_datasets(item: BaseItem) -> Iterator[LeafItem]:
    if item.type == "group":
        assert isinstance(item, GroupItem)
        if item.items:
            for child_item in item.items:
                yield from get_leaf_datasets(child_item)
    else:
        assert isinstance(item, LeafItem)
        if item.releases:
            yield item
