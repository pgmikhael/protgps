import traceback, warnings
import argparse
from typing import List, Literal
from abc import ABCMeta, abstractmethod
import json
from collections import Counter
import numpy as np
from torch.utils import data
from protgps.utils.classes import ProtGPS, set_protgps_type, classproperty
from protgps.utils.messages import METAFILE_NOTFOUND_ERR, LOAD_FAIL_MSG
import pickle


class AbstractDataset(data.Dataset, ProtGPS):
    def __init__(self, args: argparse.ArgumentParser, split_group: str) -> None:
        """
        Abstract Dataset
        params: args - config.
        params: split_group - ['train'|'dev'|'test'].

        constructs: standard pytorch Dataset obj, which can be fed in a DataLoader for batching
        """
        __metaclass__ = ABCMeta

        super(AbstractDataset, self).__init__()

        self.split_group = split_group
        self.args = args

        self.init_class(args, split_group)

        self.dataset = self.create_dataset(split_group)
        if len(self.dataset) == 0:
            return

        self.set_sample_weights(args)

        self.print_summary_statement(self.dataset, split_group)

    def init_class(self, args: argparse.ArgumentParser, split_group: str) -> None:
        """Perform Class-Specific init methods
           Default is to load JSON dataset

        Args:
            args (argparse.ArgumentParser)
            split_group (str)
        """
        self.load_dataset(args)

    def load_dataset(self, args: argparse.ArgumentParser) -> None:
        """Loads dataset file

        Args:
            args (argparse.ArgumentParser)

        Raises:
            Exception: Unable to load
        """
        try:
            self.metadata_json = json.load(open(args.dataset_file_path, "r"))
        except Exception as e:
            raise Exception(METAFILE_NOTFOUND_ERR.format(args.dataset_file_path, e))

    @abstractmethod
    def create_dataset(
        self, split_group: Literal["train", "dev", "test"]
    ) -> List[dict]:
        """
        Creates the dataset of samples from json metadata file.
        """
        pass

    @abstractmethod
    def skip_sample(self, sample) -> bool:
        """
        Return True if sample should be skipped and not included in data
        """
        return False

    @abstractmethod
    def check_label(self, sample) -> bool:
        """
        Return True if the row contains a valid label for the task
        """
        pass

    @abstractmethod
    def get_label(self, sample):
        """
        Get task specific label for a given sample
        """
        pass

    @property
    @abstractmethod
    def SUMMARY_STATEMENT(self) -> None:
        """
        Prints summary statement with dataset stats
        """
        pass

    def print_summary_statement(self, dataset, split_group):
        statement = "{} DATASET CREATED FOR {}.\n{}".format(
            split_group.upper(), self.args.dataset_name.upper(), self.SUMMARY_STATEMENT
        )
        print(statement)

    def __len__(self) -> int:
        return len(self.dataset)

    @abstractmethod
    def __getitem__(self, index):
        """
        Fetch single sample from dataset

        Args:
            index (int): random index of sample from dataset

        Returns:
            sample (dict): a sample
        """
        sample = self.dataset[index]
        try:
            return sample
        except Exception:
            warnings.warn(
                LOAD_FAIL_MSG.format(sample["sample_id"], traceback.print_exc())
            )

    def assign_splits(self, metadata_json, split_probs, seed=0) -> None:
        """
        Assign samples to data splits

        Args:
            metadata_json (dict): raw json dataset loaded
        """
        np.random.seed(seed)
        if self.args.split_type == "random":
            for idx in range(len(metadata_json)):
                if metadata_json[idx] is None:
                    continue
                metadata_json[idx]["split"] = np.random.choice(
                    ["train", "dev", "test"], p=split_probs
                )
        elif self.args.split_type == "mmseqs":
            # mmseqs easy-cluster --min-seq-id 0.3 -c 0.8
            # get all samples
            to_split = {}

            row2clust = pickle.load(
                open(
                    "data/mmseqs_row2cluster_30seq_80cov.p",
                    "rb",
                )
            )
            # rule id
            clusters = list(row2clust.values())
            clust2count = Counter(clusters)
            samples = sorted(list(set(clusters)))
            np.random.shuffle(samples)
            samples_cumsum = np.cumsum([clust2count[s] for s in samples])
            # Find the indices for each quantile
            split_indices = [
                np.searchsorted(
                    samples_cumsum, np.round(q, 3) * samples_cumsum[-1], side="right"
                )
                for q in np.cumsum(split_probs)
            ]
            split_indices[-1] = len(samples)
            split_indices = np.concatenate([[0], split_indices])
            for i in range(len(split_indices) - 1):
                to_split.update(
                    {
                        sample: ["train", "dev", "test"][i]
                        for sample in samples[split_indices[i] : split_indices[i + 1]]
                    }
                )
            for idx in range(len(metadata_json)):
                metadata_json[idx]["split"] = to_split[row2clust[idx]]

    def set_sample_weights(self, args: argparse.ArgumentParser) -> None:
        """
        Set weights for each sample

        Args:
            args (argparse.ArgumentParser)
        """
        if args.class_bal:
            label_dist = [str(d[args.class_bal_key]) for d in self.dataset]
            label_counts = Counter(label_dist)
            weight_per_label = 1.0 / len(label_counts)
            label_weights = {
                label: weight_per_label / count for label, count in label_counts.items()
            }

            print("Class counts are: {}".format(label_counts))
            print("Label weights are {}".format(label_weights))
            self.weights = [
                label_weights[str(d[args.class_bal_key])] for d in self.dataset
            ]
        else:
            pass

    @classproperty
    def DATASET_ITEM_KEYS(cls) -> list:
        """
        List of keys to be included in sample when being batched

        Returns:
            list
        """
        standard = ["sample_id"]
        return standard

    @staticmethod
    def add_args(parser) -> None:
        """Add class specific args

        Args:
            parser (argparse.ArgumentParser): argument parser
        """
        parser.add_argument(
            "--class_bal", action="store_true", default=False, help="class balance"
        )
        parser.add_argument(
            "--class_bal_key",
            type=str,
            default="y",
            help="dataset key to use for class balancing",
        )
        parser.add_argument(
            "--dataset_file_path",
            type=str,
            default=None,
            help="Path to dataset file",
        )
        parser.add_argument(
            "--data_dir",
            type=str,
            default=None,
            help="Path to dataset directory",
        )
        parser.add_argument(
            "--num_classes", type=int, default=6, help="Number of classes to predict"
        )
        # Alternative training/testing schemes
        parser.add_argument(
            "--assign_splits",
            action="store_true",
            default=False,
            help="Whether to assign different splits than those predetermined in dataset",
        )
        parser.add_argument(
            "--split_type",
            type=str,
            default="random",
            help="How to split dataset if assign_split = True..",
        )
        parser.add_argument(
            "--split_probs",
            type=float,
            nargs="+",
            default=[0.6, 0.2, 0.2],
            help="Split probs for datasets without fixed train dev test. ",
        )
        parser.add_argument(
            "--split_seed",
            type=int,
            default=0,
            help="seed for consistent randomization",
        )
