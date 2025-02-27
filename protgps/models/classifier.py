import torch
import torch.nn as nn
import copy
from protgps.utils.registry import register_object, get_object
from protgps.utils.classes import set_protgps_type
from protgps.models.abstract import AbstractModel


@register_object("classifier", "model")
class Classifier(AbstractModel):
    def __init__(self, args):
        super(Classifier, self).__init__()

        self.args = args
        self.encoder = get_object(args.model_name_for_encoder, "model")(args)
        cargs = copy.deepcopy(args)
        self.mlp = get_object("mlp_classifier", "model")(cargs)

    def forward(self, batch=None):
        output = {}
        output["encoder_hidden"] = self.encoder(batch)["hidden"]
        output.update(self.mlp({"x": output["encoder_hidden"]}))
        return output

    @staticmethod
    def add_args(parser) -> None:
        """Add class specific args

        Args:
            parser (argparse.ArgumentParser): argument parser
        """
        parser.add_argument(
            "--model_name_for_encoder",
            type=str,
            action=set_protgps_type("model"),
            default="resnet18",
            help="Name of encoder to use",
        )
        parser.add_argument(
            "--mlp_input_dim", type=int, default=512, help="Dim of input to mlp"
        )
        parser.add_argument(
            "--mlp_layer_configuration",
            type=int,
            nargs="*",
            default=[128, 128],
            help="MLP layer dimensions",
        )
        parser.add_argument(
            "--mlp_use_batch_norm",
            action="store_true",
            default=False,
            help="Use batchnorm in mlp",
        )
        parser.add_argument(
            "--mlp_use_layer_norm",
            action="store_true",
            default=False,
            help="Use LayerNorm in mlp",
        )


@register_object("mlp_classifier", "model")
class MLPClassifier(AbstractModel):
    def __init__(self, args):
        super(MLPClassifier, self).__init__()

        self.args = args

        model_layers = []
        cur_dim = args.mlp_input_dim
        for layer_size in args.mlp_layer_configuration:
            model_layers.extend(self.append_layer(cur_dim, layer_size, args))
            cur_dim = layer_size

        self.mlp = nn.Sequential(*model_layers)
        self.predictor = nn.Linear(cur_dim, args.num_classes)

    def append_layer(self, cur_dim, layer_size, args, with_dropout=True):
        linear_layer = nn.Linear(cur_dim, layer_size)
        bn = nn.BatchNorm1d(layer_size)
        ln = nn.LayerNorm(layer_size)
        if args.mlp_use_batch_norm:
            seq = [linear_layer, bn, nn.ReLU()]
        elif args.mlp_use_layer_norm:
            seq = [linear_layer, ln, nn.ReLU()]
        else:
            seq = [linear_layer, nn.ReLU()]
        if with_dropout:
            seq.append(nn.Dropout(p=args.dropout))
        return seq

    def forward(self, batch=None):
        output = {}
        z = self.mlp(batch["x"])
        output["logit"] = self.predictor(z)
        output["hidden"] = z
        return output

    @staticmethod
    def add_args(parser):
        parser.add_argument(
            "--mlp_input_dim", type=int, default=512, help="Dim of input to mlp"
        )
        parser.add_argument(
            "--mlp_layer_configuration",
            type=int,
            nargs="*",
            default=[128, 128],
            help="MLP layer dimensions",
        )
        parser.add_argument(
            "--mlp_use_batch_norm",
            action="store_true",
            default=False,
            help="Use batchnorm in mlp",
        )
        parser.add_argument(
            "--mlp_use_layer_norm",
            action="store_true",
            default=False,
            help="Use LayerNorm in mlp",
        )
