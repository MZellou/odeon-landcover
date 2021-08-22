import os
import json
from odeon.commons.reports.report import Report


class Report_Multiclass(Report):

    def __init__(self, input_object):
        """Init function of a Metric_Report object.

        Parameters
        ----------
        input_object : Metrics
            Object Metric with the results to export in a report.
        """
        super().__init__(input_object)

    def create_data(self):
        if self.input_object.output_type != 'json':
            self.path_cm_micro = self.input_object.plot_confusion_matrix(self.input_object.cm_micro,
                                                                         labels=self.input_object.class_labels,
                                                                         name_plot='cm_micro.png')

            self.path_cm_macro = self.input_object.plot_confusion_matrix(self.input_object.cm_macro,
                                                                         labels=['Positive', 'Negative'],
                                                                         name_plot='cm_macro.png')

        if self.input_object.get_calibration_curves and not self.input_object.type_prob == 'hard':
            self.path_calibration_curves = self.input_object.plot_calibration_curve()

        if self.input_object.get_ROC_PR_curves:
            self.ROC_PR_classes = self.input_object.plot_ROC_PR_per_class()

        if self.input_object.get_hists_per_metrics:
            self.path_metrics_hists = self.input_object.plot_dataset_metrics_histograms()

    def to_json(self):
        """Create a report in the json format.
        """
        dict_export = self.input_object.dict_export
        dict_export['cm micro'] = self.input_object.cm_micro.tolist()
        dict_export['cm macro'] = self.input_object.cm_macro.tolist()
        dict_export['report macro'] = self.round_df_values(self.input_object.df_report_macro).T.to_dict()
        dict_export['report micro'] = self.round_df_values(self.input_object.df_report_micro).T.to_dict()
        dict_export['report classes'] = self.round_df_values(self.input_object.df_report_classes).T.to_dict()

        with open(os.path.join(self.input_object.output_path, 'report_metrics.json'), "w") as output_file:
            json.dump(dict_export, output_file, indent=4)

    def to_md(self):
        """Create a report in the markdown format.
        """
        md_main = f"""
# ODEON - Metrics

## Macro Strategy

### Metrics
{self.df_to_md(self.round_df_values(self.input_object.df_report_macro))}

### Confusion matrix
![Confusion matrix macro](./{os.path.basename(self.path_cm_macro)})


## Micro Strategy

### Metrics
{self.df_to_md(self.round_df_values(self.input_object.df_report_micro))}

### Confusion matrix
![Confusion matrix micro](./{os.path.basename(self.path_cm_micro)})


## Per Class Strategy

### Metrics
{self.df_to_md(self.round_df_values(self.input_object.df_report_classes))}

"""
        md_elements = [md_main]

        if self.input_object.get_calibration_curves and not self.input_object.type_prob == 'hard':
            calibration_curves = f"""
## Calibration Curves
![Calibration curves](./{os.path.basename(self.path_calibration_curves)})
"""
            md_elements.append(calibration_curves)

        if self.input_object.get_ROC_PR_curves:
            roc_pr_curves = f"""
## Roc PR Curves
![Roc PR curves](./{os.path.basename(self.ROC_PR_classes)})
"""
            md_elements.append(roc_pr_curves)

        if self.input_object.get_hists_per_metrics:
            metrics_histograms = f"""
## Metrics Histograms
![Histograms per metric](./{os.path.basename(self.path_metrics_hists)})
"""
            md_elements.append(metrics_histograms)

        with open(os.path.join(self.input_object.output_path, 'multiclass_metrics.md'), "w") as output_file:
            for md_element in md_elements:
                output_file.write(md_element)

    def to_html(self):
        """Create a report in the html format.
        """
        with open(self.html_file, "r") as reader:
            begin_html = reader.read()

        header_html = """
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0">

        <title>ODEON Metrics</title>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/require.js/2.1.10/require.min.js">
        </script>
        """

        end_html = '</div></div></body></html>'

        main_html = f"""
            <h1><center> ODEON  Metrics</center></h1>
            <h2>Macro Strategy</h2>
            <h3>* Metrics</h3>
            {self.df_to_html(self.round_df_values(self.input_object.df_report_macro))}
            <h3>* Confusion Matrix</h3>
            <p><img alt="Macro Confusion Matrix" src=./{os.path.basename(self.path_cm_macro)} /></p>
            <h2>Micro Strategy</h2>
            <h3>* Metrics</h3>
            {self.df_to_html(self.round_df_values(self.input_object.df_report_micro))}
            <h3>* Confusion Matrix</h3>
            <p><img alt="Macro Confusion Matrix" src=./{os.path.basename(self.path_cm_micro)} /></p>

            <h2>Per class Strategy</h2>
            <h3>* Metrics</h3>
            {self.df_to_html(self.round_df_values(self.input_object.df_report_classes))}
            """

        html_elements = [header_html, begin_html, main_html]

        if self.input_object.get_calibration_curves and not self.input_object.type_prob == 'hard':
            calibration_curves = f"""
            <h3>* Calibration Curves</h3>
            <p><img alt="Calibration Curve" src=./{os.path.basename(self.path_calibration_curves)} /></p>
            """
            html_elements.append(calibration_curves)

        if self.input_object.get_ROC_PR_curves:
            roc_pr_curves = f"""
            <h3>* ROC and PR Curves</h3>
            <p><img alt="ROC and PR Curves" src=./{os.path.basename(self.ROC_PR_classes)} /></p>
            """
            html_elements.append(roc_pr_curves)

        if self.input_object.get_hists_per_metrics:
            metrics_histograms = f"""
            <h2>Metrics Histograms</h2>
            <p><img alt="Metrics Histograms" src=./{os.path.basename(self.path_metrics_hists)} /></p>
            """
            html_elements.append(metrics_histograms)

        html_elements.append(end_html)

        with open(os.path.join(self.input_object.output_path, 'metrics_multiclass.html'), "w") as output_file:
            for html_part in html_elements:
                output_file.write(html_part)
