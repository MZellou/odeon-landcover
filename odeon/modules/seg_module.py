import pytorch_lightning as pl
import torch
from torchmetrics import MeanMetric

from odeon.metrics.metrics_module import OdeonMetrics
from odeon.models.base import build_model
from odeon.nn.losses import build_loss_function
from odeon.nn.optim import build_optimizer, build_scheduler

DEFAULT_CRITERION = "ce"
DEFAULT_LR = 0.01


class SegmentationTask(pl.LightningModule):
    def __init__(
        self,
        model_name,
        num_classes,
        num_channels,
        class_labels,
        criterion_name=DEFAULT_CRITERION,
        learning_rate=DEFAULT_LR,
        optimizer_config=None,
        scheduler_config=None,
        loss_classes_weights=None,
        deterministic=False,
    ):

        super().__init__()
        self.model_name = model_name
        self.num_classes = num_classes
        self.num_channels = num_channels
        self.class_labels = class_labels
        self.criterion_name = criterion_name
        self.learning_rate = learning_rate
        self.optimizer_config = optimizer_config
        self.scheduler_config = scheduler_config
        self.loss_classes_weights = (
            None if loss_classes_weights is None else loss_classes_weights
        )
        self.deterministic = deterministic

        # Variables not stocked in hparams dict
        self.model = None
        self.criterion = None
        self.optimizer = None
        self.scheduler = None
        self.samples = None
        self.idx_csv_loggers = None

        self.save_hyperparameters(
            "model_name",
            "num_classes",
            "num_channels",
            "class_labels",
            "criterion_name",
            "optimizer_config",
            "learning_rate",
            "scheduler_config",
            "loss_classes_weights",
            "deterministic",
        )

    def setup(self, stage=None):
        if self.model is None:
            self.model = build_model(
                model_name=self.hparams.model_name,
                n_channels=self.hparams.num_channels,
                n_classes=self.hparams.num_classes,
                deterministic=self.hparams.deterministic,
            )
        if self.criterion is None:
            self.criterion = build_loss_function(
                self.hparams.criterion_name, self.hparams.loss_classes_weights
            )

        if stage == "fit":
            self.train_epoch_loss, self.val_epoch_loss = None, None
            self.train_epoch_metrics, self.val_epoch_metrics = None, None
            self.train_metrics = OdeonMetrics(
                num_classes=self.hparams.num_classes,
                class_labels=self.hparams.class_labels,
                deterministic=self.deterministic,
            )
            self.val_metrics = OdeonMetrics(
                num_classes=self.hparams.num_classes,
                class_labels=self.hparams.class_labels,
                deterministic=self.deterministic,
            )
            self.train_loss = MeanMetric()
            self.val_loss = MeanMetric()

        elif stage == "validate":
            self.val_epoch_loss, self.val_epoch_metrics = None, None
            self.val_metrics = OdeonMetrics(
                num_classes=self.hparams.num_classes,
                class_labels=self.hparams.class_labels,
                deterministic=self.deterministic,
            )
            self.val_loss = MeanMetric()

        elif stage == "test":
            self.test_epoch_loss, self.test_epoch_metrics = None, None
            self.test_metrics = OdeonMetrics(
                num_classes=self.hparams.num_classes,
                class_labels=self.hparams.class_labels,
                deterministic=self.deterministic,
            )
            self.test_loss = MeanMetric()

        elif stage == "predict":
            self.predict_epoch_loss, self.predict_epoch_metrics = None, None
            self.predict_metrics = OdeonMetrics(
                num_classes=self.hparams.num_classes,
                class_labels=self.hparams.class_labels,
                deterministic=self.deterministic,
            )
            self.predict_loss = MeanMetric()

    def forward(self, images):
        logits = self.model(images)
        return logits

    def step(self, batch):
        images, targets = batch["image"], batch["mask"]
        logits = self.forward(images)

        if self.deterministic:
            torch.use_deterministic_algorithms(False)

        loss = self.criterion(logits, targets)

        if self.deterministic:
            torch.use_deterministic_algorithms(True)

        with torch.no_grad():
            proba = torch.softmax(logits, dim=1)
            preds = torch.argmax(proba, dim=1)
            targets = torch.argmax(targets, dim=1)
            # Change shapes and cast target to integer for metrics computation
            preds = preds.flatten(start_dim=1)
            targets = targets.flatten(start_dim=1).type(torch.int32)
        return loss, preds, targets

    def training_step(self, batch, batch_idx):
        loss, preds, targets = self.step(batch)
        return {"loss": loss, "preds": preds, "targets": targets}

    def training_step_end(self, step_output):
        loss, preds, targets = (
            step_output["loss"].mean(),
            step_output["preds"],
            step_output["targets"],
        )
        self.train_loss.update(loss)
        self.train_metrics(preds=preds, target=targets)
        return loss

    def training_epoch_end(self, outputs):
        self.train_epoch_loss = self.train_loss.compute()
        self.train_epoch_metrics = self.train_metrics.compute()
        self.log(
            "train_loss",
            self.train_epoch_loss,
            on_step=False,
            on_epoch=True,
            prog_bar=True,
            logger=False,
        )
        self.train_loss.reset()
        self.train_metrics.reset()

    def validation_step(self, batch, batch_idx):
        loss, preds, targets = self.step(batch)
        return {"loss": loss, "preds": preds, "targets": targets}

    def validation_step_end(self, step_output):
        loss, preds, targets = (
            step_output["loss"].mean(),
            step_output["preds"],
            step_output["targets"],
        )
        self.val_loss.update(loss)
        self.val_metrics(preds=preds, target=targets)
        return loss

    def validation_epoch_end(self, outputs):
        self.val_epoch_loss = self.val_loss.compute()
        self.val_epoch_metrics = self.val_metrics.compute()
        # self.log: log metrics we want to monitor for model selection in checkpoints creation
        self.log(
            "val_loss",
            self.val_epoch_loss,
            on_step=False,
            on_epoch=True,
            prog_bar=True,
            logger=False,
        )
        self.log(
            "val_miou",
            self.val_epoch_metrics["Average/IoU"],
            on_step=False,
            on_epoch=True,
            prog_bar=True,
            logger=False,
        )
        # self.scheduler_step(self.val_epoch_loss)
        self.val_loss.reset()
        self.val_metrics.reset()

    def test_step(self, batch, batch_idx):
        loss, preds, targets = self.step(batch)
        return {"loss": loss, "preds": preds, "targets": targets}

    def test_step_end(self, step_output):
        loss, preds, targets = (
            step_output["loss"].mean(),
            step_output["preds"],
            step_output["targets"],
        )
        self.test_loss.update(loss)
        self.test_metrics(preds=preds, target=targets)
        return loss

    def test_epoch_end(self, outputs):
        self.test_epoch_loss = self.test_loss.compute()
        self.test_epoch_metrics = self.test_metrics.compute()
        self.test_loss.reset()
        self.test_metrics.reset()

    def predict_step(self, batch, batch_idx, dataloader_idx=0):
        logits = self.model(batch["image"])
        batch["proba"] = torch.softmax(logits, dim=1)
        return batch

    def scheduler_step(self, monitored_metric=None):
        sch = self.lr_schedulers()
        if isinstance(sch, torch.optim.lr_scheduler.ReduceLROnPlateau):
            sch.step(monitored_metric)
        else:
            sch.step()

    def configure_optimizers(self):
        if self.optimizer is None:
            self.optimizer = build_optimizer(
                params=self.model.parameters(),
                learning_rate=self.hparams.learning_rate,
                optimizer_config=self.hparams.optimizer_config,
            )

        if self.scheduler is None:
            self.scheduler = build_scheduler(
                optimizer=self.optimizer, scheduler_config=self.hparams.scheduler_config
            )

        lr_scheduler_config = {
            "scheduler": self.scheduler,
            "interval": "epoch",
            "monitor": "val_loss",
            "frequency": 1,
            "strict": True,
            "name": "LR Scheduler",
        }

        config = {"optimizer": self.optimizer, "lr_scheduler": lr_scheduler_config}

        return config

    def on_save_checkpoint(self, checkpoint):
        return super().on_save_checkpoint(checkpoint)

    def on_load_checkpoint(self, checkpoint):
        return super().on_load_checkpoint(checkpoint)
