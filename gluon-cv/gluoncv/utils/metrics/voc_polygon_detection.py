"""Pascal VOC Polygon Points Detection evaluation."""
from __future__ import division

from collections import defaultdict
import numpy as np
import mxnet as mx
from ..bbox import coef_polygon_iou, new_iou
from PIL import Image
import os

class VOCPolygonMApMetric(mx.metric.EvalMetric):
    """
    Calculate mean AP for ESE-Seg task (Polygon mAP)

    Parameters:
    ---------
    iou_thresh : float
        IOU overlap threshold for TP
    class_names : list of str
        optional, if provided, will print out AP for each class
    """
    def __init__(self, iou_thresh=0.5, class_names=None):
        super(VOCPolygonMApMetric, self).__init__('VOCMeanAP')
        if class_names is None:
            self.num = None
        else:
            assert isinstance(class_names, (list, tuple))
            for name in class_names:
                assert isinstance(name, str), "must provide names as str"
            num = len(class_names)
            self.name = list(class_names) + ['mAP']
            self.num = num + 1
        self.reset()
        self.iou_thresh = iou_thresh
        self.class_names = class_names
        self.bases = np.load('/home/tutian/dataset/sbd/all_50_1.npy')

    def reset(self):
        """Clear the internal statistics to initial state."""
        if getattr(self, 'num', None) is None:
            self.num_inst = 0
            self.sum_metric = 0.0
        else:
            self.num_inst = [0] * self.num
            self.sum_metric = [0.0] * self.num
        self._n_pos = defaultdict(int)
        self._score = defaultdict(list)
        self._match = defaultdict(list)

    def get(self):
        """Get the current evaluation result.

        Returns
        -------
        name : str
           Name of the metric.
        value : float
           Value of the evaluation.
        """
        self._update()  # update metric at this time
        if self.num is None:
            if self.num_inst == 0:
                return (self.name, float('nan'))
            else:
                return (self.name, self.sum_metric / self.num_inst)
        else:
            names = ['%s'%(self.name[i]) for i in range(self.num)]
            values = [x / y if y != 0 else float('nan') \
                for x, y in zip(self.sum_metric, self.num_inst)]
            return (names, values)

    def update(self, pred_bboxes, pred_coefs, pred_labels, pred_scores,
               gt_bboxes, gt_points_xs, gt_points_ys, gt_labels, widths, heights, gt_difficults=None, gt_coefs=None, gt_imgids=None):
        """Update internal buffer with latest prediction and gt pairs.

        Parameters
        ----------
        pred_bboxes : mxnet.NDArray or numpy.ndarray
            Prediction bounding boxes with shape `B, N, 4`.
            Where B is the size of mini-batch, N is the number of bboxes.
        pred_labels : mxnet.NDArray or numpy.ndarray
            Prediction bounding boxes labels with shape `B, N`.
        pred_coefs  : mxnet.NDArray or numpy.ndarray
            Prediction coefs with shape `B , N , coefficient num`.
        pred_scores : mxnet.NDArray or numpy.ndarray
            Prediction bounding boxes scores with shape `B, N`.
        gt_bboxes : mxnet.NDArray or numpy.ndarray
            Ground-truth bounding boxes with shape `B, M, 4`.
            Where B is the size of mini-batch, M is the number of ground-truths.
        gt_labels : mxnet.NDArray or numpy.ndarray
            Ground-truth bounding boxes labels with shape `B, M`.
        gt_points_xs : mxnet.NDArray or numpy.ndarray
            points_xs label with shape `B, N, 360`
        gt_points_ys : mxnet.NDArray or numpy.ndarray
            points_ys label with shape `B, N, 360`
        gt_difficults : mxnet.NDArray or numpy.ndarray, optional, default is None
            Ground-truth bounding boxes difficulty labels with shape `B, M`.
        imgs_shape : mxnet.NDArray or numpy.ndarray
            imgs_shape with shape `B, 2 `  (img_w,img_h)
        """
        def as_numpy(a):
            """Convert a (list of) mx.NDArray into numpy.ndarray"""
            if isinstance(a, (list, tuple)):
                out = [x.asnumpy() if isinstance(x, mx.nd.NDArray) else x for x in a]
                try:
                    out = np.concatenate(out, axis=0)
                except ValueError:
                    out = np.array(out)
                return out
            elif isinstance(a, mx.nd.NDArray):
                a = a.asnumpy()
            return a

        if gt_difficults is None:
            gt_difficults = [None for _ in as_numpy(gt_labels)]

        if gt_coefs is None:  # For analysis
            gt_coefs = [None for _ in as_numpy(gt_labels)]
        if gt_imgids is None:  # For analysis
            gt_imgids = [None for _ in as_numpy(gt_labels)]

        for pred_bbox, pred_coef, pred_label, pred_score, gt_bbox, gt_points_xs, gt_points_ys, gt_label, gt_difficult, width_array, height_array, gt_coef, gt_imgid  in zip(
                *[as_numpy(x) for x in [pred_bboxes, pred_coefs, pred_labels, pred_scores,
                                        gt_bboxes, gt_points_xs, gt_points_ys, gt_labels, gt_difficults, widths, heights,
                                        gt_coefs, gt_imgids]]):
            # strip padding -1 for pred and gt
            valid_pred = np.where(pred_label.flat >= 0)[0]
            pred_bbox = pred_bbox[valid_pred, :]
            # pred_center = pred_center[valid_pred, :]
            pred_coef = pred_coef[valid_pred, :]
            pred_label = pred_label.flat[valid_pred].astype(int)
            pred_score = pred_score.flat[valid_pred]
            valid_gt = np.where(gt_label.flat >= 0)[0]
            gt_bbox = gt_bbox[valid_gt, :]
            gt_points_xs = gt_points_xs[valid_gt, :]
            gt_points_ys = gt_points_ys[valid_gt, :]
            gt_coef = gt_coef[valid_gt, :]
            gt_imgid = gt_imgid[valid_gt, :]
            gt_label = gt_label.flat[valid_gt].astype(int)
            if gt_difficult is None:
                gt_difficult = np.zeros(gt_bbox.shape[0])
            else:
                gt_difficult = gt_difficult.flat[valid_gt]

            for l in np.unique(np.concatenate((pred_label, gt_label)).astype(int)):
                pred_mask_l = pred_label == l
                pred_bbox_l = pred_bbox[pred_mask_l]
                # pred_center_l = pred_center[pred_mask_l]
                pred_coef_l = pred_coef[pred_mask_l]
                pred_score_l = pred_score[pred_mask_l]
                # sort by score
                order = pred_score_l.argsort()[::-1]
                pred_bbox_l = pred_bbox_l[order]
                # pred_center_l = pred_center_l[order]
                pred_coef_l = pred_coef_l[order]
                pred_score_l = pred_score_l[order]

                gt_mask_l = gt_label == l
                gt_bbox_l = gt_bbox[gt_mask_l]
                gt_coef_l = gt_coef[gt_mask_l]
                gt_imgid_l = gt_imgid[gt_mask_l]
                gt_points_xs_l = gt_points_xs[gt_mask_l]
                gt_points_ys_l = gt_points_ys[gt_mask_l]
                gt_difficult_l = gt_difficult[gt_mask_l]

                self._n_pos[l] += np.logical_not(gt_difficult_l).sum()
                self._score[l].extend(pred_score_l)

                if len(pred_bbox_l) == 0:
                    continue
                if len(gt_bbox_l) == 0:
                    self._match[l].extend((0,) * pred_bbox_l.shape[0])
                    continue
                pred_bbox_l = pred_bbox_l.copy()
                # pred_center_l = pred_center_l.copy()
                pred_coef_l = pred_coef_l.copy()
                gt_bbox_l = gt_bbox_l.copy()
                gt_points_xs_l = gt_points_xs_l.copy()
                gt_points_ys_l = gt_points_ys_l.copy()
                iou = coef_polygon_iou(pred_coef_l, self.bases, pred_bbox_l, gt_points_xs_l, gt_points_ys_l)
                # iou: shape [pd, gt]
                gt_index = iou.argmax(axis=1)  # gt_index[pd] = gt_id
                # set -1 if there is no matching ground truth
                gt_index[iou.max(axis=1) < self.iou_thresh] = -1
                del iou

                # print(np.unique(gt_imgid_l))
                # coef_analysis_var_first_20_label
                # coef_analysis_uniform_50_label
                with open(f'/home/tutian/coef_analysis_var_first_20_label/{int(np.unique(gt_imgid_l)[0])}.txt', 'a+') as f:
                    for (pd, gt) in enumerate(gt_index):
                        if gt == -1:
                            continue
                        to_write = str(gt_coef_l[gt])+str(pred_coef_l[pd])+ str(gt_bbox_l[gt])+str(pred_bbox_l[pd]) + str(gt_label[gt]) + ' '+ str(pred_label[pd])
                        to_write = to_write.replace('[', ' ').replace(']', ' ').strip().replace('\n', ' ')

                        f.writelines(to_write + '\n')

                selec = np.zeros(gt_bbox_l.shape[0], dtype=bool)
                for gt_idx in gt_index:
                    if gt_idx >= 0:
                        if gt_difficult_l[gt_idx]:
                            self._match[l].append(-1)
                        else:
                            if not selec[gt_idx]:
                                self._match[l].append(1)
                            else:
                                self._match[l].append(0)
                        selec[gt_idx] = True
                    else:
                        self._match[l].append(0)

    def _update(self):
        """ update num_inst and sum_metric """
        aps = []
        recall, precs = self._recall_prec()
        for l, rec, prec in zip(range(len(precs)), recall, precs):
            ap = self._average_precision(rec, prec)
            aps.append(ap)
            if self.num is not None and l < (self.num - 1):
                self.sum_metric[l] = ap
                self.num_inst[l] = 1
        if self.num is None:
            self.num_inst = 1
            self.sum_metric = np.nanmean(aps)
        else:
            self.num_inst[-1] = 1
            self.sum_metric[-1] = np.nanmean(aps)

    def _recall_prec(self):
        """ get recall and precision from internal records """
        n_fg_class = max(self._n_pos.keys()) + 1
        prec = [None] * n_fg_class
        rec = [None] * n_fg_class

        for l in self._n_pos.keys():
            score_l = np.array(self._score[l])
            match_l = np.array(self._match[l], dtype=np.int32)

            order = score_l.argsort()[::-1]
            match_l = match_l[order]

            tp = np.cumsum(match_l == 1)
            fp = np.cumsum(match_l == 0)

            # If an element of fp + tp is 0,
            # the corresponding element of prec[l] is nan.
            with np.errstate(divide='ignore', invalid='ignore'):
                prec[l] = tp / (fp + tp)
            # If n_pos[l] is 0, rec[l] is None.
            if self._n_pos[l] > 0:
                rec[l] = tp / self._n_pos[l]

        return rec, prec

    def _average_precision(self, rec, prec):
        """
        calculate average precision

        Params:
        ----------
        rec : numpy.array
            cumulated recall
        prec : numpy.array
            cumulated precision
        Returns:
        ----------
        ap as float
        """
        if rec is None or prec is None:
            return np.nan

        # append sentinel values at both ends
        mrec = np.concatenate(([0.], rec, [1.]))
        mpre = np.concatenate(([0.], np.nan_to_num(prec), [0.]))

        # compute precision integration ladder
        for i in range(mpre.size - 1, 0, -1):
            mpre[i - 1] = np.maximum(mpre[i - 1], mpre[i])

        # look for recall value changes
        i = np.where(mrec[1:] != mrec[:-1])[0]

        # sum (\delta recall) * prec
        ap = np.sum((mrec[i + 1] - mrec[i]) * mpre[i + 1])
        return ap


class VOC07PolygonMApMetric(VOCPolygonMApMetric):
    """ Mean average precision metric for PASCAL V0C 07 dataset

    Parameters:
    ---------
    iou_thresh : float
        IOU overlap threshold for TP
    class_names : list of str
        optional, if provided, will print out AP for each class

    """
    def __init__(self, *args, **kwargs):
        super(VOC07PolygonMApMetric, self).__init__(*args, **kwargs)

    def _average_precision(self, rec, prec):
        """
        calculate average precision, override the default one,
        special 11-point metric

        Params:
        ----------
        rec : numpy.array
            cumulated recall
        prec : numpy.array
            cumulated precision
        Returns:
        ----------
        ap as float
        """
        if rec is None or prec is None:
            return np.nan
        ap = 0.
        for t in np.arange(0., 1.1, 0.1):
            if np.sum(rec >= t) == 0:
                p = 0
            else:
                p = np.max(np.nan_to_num(prec)[rec >= t])
            ap += p / 11.
        return ap


class NewPolygonMApMetric(mx.metric.EvalMetric):
    """
    Calculate mean AP for ESE-Seg task (Polygon mAP)

    Parameters:
    ---------
    iou_thresh : float
        IOU overlap threshold for TP
    class_names : list of str
        optional, if provided, will print out AP for each class
    """
    def __init__(self, iou_thresh=0.5, class_names=None, root=None):
        super(NewPolygonMApMetric, self).__init__('VOCMeanAP')
        if class_names is None:
            self.num = None
        else:
            assert isinstance(class_names, (list, tuple))
            for name in class_names:
                assert isinstance(name, str), "must provide names as str"
            num = len(class_names)
            self.name = list(class_names) + ['mAP']
            self.num = num + 1
        self.reset()
        self.iou_thresh = iou_thresh
        self.class_names = class_names
        bases_root = '/home/tutian/dataset/coco_to_voc/coco_all_50_1.npy'
        print(f"Metric is loading {bases_root}")
        self.bases = np.load(bases_root)
        self.root = root

    def reset(self):
        """Clear the internal statistics to initial state."""
        if getattr(self, 'num', None) is None:
            self.num_inst = 0
            self.sum_metric = 0.0
        else:
            self.num_inst = [0] * self.num
            self.sum_metric = [0.0] * self.num
        self._n_pos = defaultdict(int)
        self._score = defaultdict(list)
        self._match = defaultdict(list)

    def get(self):
        """Get the current evaluation result.

        Returns
        -------
        name : str
           Name of the metric.
        value : float
           Value of the evaluation.
        """
        self._update()  # update metric at this time
        if self.num is None:
            if self.num_inst == 0:
                return (self.name, float('nan'))
            else:
                return (self.name, self.sum_metric / self.num_inst)
        else:
            names = ['%s'%(self.name[i]) for i in range(self.num)]
            values = [x / y if y != 0 else float('nan') \
                for x, y in zip(self.sum_metric, self.num_inst)]
            return (names, values)

    def update(self, pred_bboxes, pred_coefs, pred_labels, pred_scores,
               gt_bboxes, gt_labels, widths, heights, gt_difficults=None, gt_coefs=None, gt_imgids=None, gt_inst_ids=None):
        """Update internal buffer with latest prediction and gt pairs.

        Parameters
        ----------
        pred_bboxes : mxnet.NDArray or numpy.ndarray
            Prediction bounding boxes with shape `B, N, 4`.
            Where B is the size of mini-batch, N is the number of bboxes.
        pred_labels : mxnet.NDArray or numpy.ndarray
            Prediction bounding boxes labels with shape `B, N`.
        pred_coefs  : mxnet.NDArray or numpy.ndarray
            Prediction coefs with shape `B , N , coefficient num`.
        pred_scores : mxnet.NDArray or numpy.ndarray
            Prediction bounding boxes scores with shape `B, N`.
        gt_bboxes : mxnet.NDArray or numpy.ndarray
            Ground-truth bounding boxes with shape `B, M, 4`.
            Where B is the size of mini-batch, M is the number of ground-truths.
        gt_labels : mxnet.NDArray or numpy.ndarray
            Ground-truth bounding boxes labels with shape `B, M`.
        gt_difficults : mxnet.NDArray or numpy.ndarray, optional, default is None
            Ground-truth bounding boxes difficulty labels with shape `B, M`.
        imgs_shape : mxnet.NDArray or numpy.ndarray
            imgs_shape with shape `B, 2 `  (img_w,img_h)
        """
        def as_numpy(a):
            """Convert a (list of) mx.NDArray into numpy.ndarray"""
            if isinstance(a, (list, tuple)):
                out = [x.asnumpy() if isinstance(x, mx.nd.NDArray) else x for x in a]
                try:
                    out = np.concatenate(out, axis=0)
                except ValueError:
                    out = np.array(out)
                return out
            elif isinstance(a, mx.nd.NDArray):
                a = a.asnumpy()
            return a

        if gt_difficults is None:
            gt_difficults = [None for _ in as_numpy(gt_labels)]

        if gt_coefs is None:  # For analysis
            gt_coefs = [None for _ in as_numpy(gt_labels)]
        if gt_imgids is None:  # For analysis
            gt_imgids = [None for _ in as_numpy(gt_labels)]
        if gt_inst_ids is None:  # For analysis
            gt_inst_ids = [None for _ in as_numpy(gt_labels)]

        for pred_bbox, pred_coef, pred_label, pred_score, gt_bbox, gt_label, gt_difficult, width_array, height_array, gt_coef, gt_imgid, gt_inst_id  in zip(
                *[as_numpy(x) for x in [pred_bboxes, pred_coefs, pred_labels, pred_scores,
                                        gt_bboxes, gt_labels, gt_difficults, widths, heights,
                                        gt_coefs, gt_imgids, gt_inst_ids]]):
            # strip padding -1 for pred and gt
            valid_pred = np.where(pred_label.flat >= 0)[0]
            pred_bbox = pred_bbox[valid_pred, :]
            # pred_center = pred_center[valid_pred, :]
            pred_coef = pred_coef[valid_pred, :]
            pred_label = pred_label.flat[valid_pred].astype(int)
            pred_score = pred_score.flat[valid_pred]
            valid_gt = np.where(gt_label.flat >= 0)[0]
            gt_bbox = gt_bbox[valid_gt, :]
            gt_coef = gt_coef[valid_gt, :]
            gt_imgid = gt_imgid[valid_gt, :]
            assert(np.unique(gt_imgid).shape[0] == 1)
            # print(gt_inst_id)
            gt_inst_id = gt_inst_id[valid_gt, :]
            # print(gt_inst_id)

            # Load gt mask - original size!
            file_name = str(int(np.unique(gt_imgid))) + '.png'
            instance_mask = np.array(Image.open(os.path.join(self.root, 'instance_labels', file_name)))
            instance_ids = np.unique(instance_mask)
            M = 0
            for inst_id in instance_ids:
                if inst_id == 0 or inst_id == 255:
                    continue
                M += 1
            gt_masks = np.zeros((M, instance_mask.shape[0], instance_mask.shape[1]))
            M = 0
            for instance_id in instance_ids:
                if instance_id == 0 or instance_id == 255:  # background or edge, pass
                    continue
                temp = np.zeros(instance_mask.shape)
                temp.fill(instance_id)
                gt_masks[M] = (instance_mask == temp)
                M += 1
            # gt mask end
            # print(M)

            gt_label = gt_label.flat[valid_gt].astype(int)
            if gt_difficult is None:
                gt_difficult = np.zeros(gt_bbox.shape[0])
            else:
                gt_difficult = gt_difficult.flat[valid_gt]

            for l in np.unique(np.concatenate((pred_label, gt_label)).astype(int)):
                pred_mask_l = pred_label == l
                pred_bbox_l = pred_bbox[pred_mask_l]
                pred_coef_l = pred_coef[pred_mask_l]
                pred_score_l = pred_score[pred_mask_l]
                # sort by score
                order = pred_score_l.argsort()[::-1]
                pred_bbox_l = pred_bbox_l[order]
                pred_coef_l = pred_coef_l[order]
                pred_score_l = pred_score_l[order]

                gt_mask_l = gt_label == l
                gt_bbox_l = gt_bbox[gt_mask_l]
                # gt_coef_l = gt_coef[gt_mask_l]
                gt_masks_l = gt_masks[gt_mask_l]  # gt_masks and gt_mask are DIFFERENT!
                gt_difficult_l = gt_difficult[gt_mask_l]

                self._n_pos[l] += np.logical_not(gt_difficult_l).sum()
                self._score[l].extend(pred_score_l)

                if len(pred_bbox_l) == 0:
                    continue
                if len(gt_bbox_l) == 0:
                    self._match[l].extend((0,) * pred_bbox_l.shape[0])
                    continue
                pred_bbox_l = pred_bbox_l.copy()
                pred_coef_l = pred_coef_l.copy()
                gt_bbox_l = gt_bbox_l.copy()

                iou = new_iou(pred_coef_l, self.bases, pred_bbox_l, gt_masks_l)
                gt_index = iou.argmax(axis=1)  # gt_index[pd] = gt_id
                # set -1 if there is no matching ground truth
                gt_index[iou.max(axis=1) < self.iou_thresh] = -1
                del iou

                selec = np.zeros(gt_bbox_l.shape[0], dtype=bool)
                for gt_idx in gt_index:
                    if gt_idx >= 0:
                        if gt_difficult_l[gt_idx]:
                            self._match[l].append(-1)
                        else:
                            if not selec[gt_idx]:
                                self._match[l].append(1)
                            else:
                                self._match[l].append(0)
                        selec[gt_idx] = True
                    else:
                        self._match[l].append(0)

    def _update(self):
        """ update num_inst and sum_metric """
        aps = []
        recall, precs = self._recall_prec()
        for l, rec, prec in zip(range(len(precs)), recall, precs):
            ap = self._average_precision(rec, prec)
            aps.append(ap)
            if self.num is not None and l < (self.num - 1):
                self.sum_metric[l] = ap
                self.num_inst[l] = 1
        if self.num is None:
            self.num_inst = 1
            self.sum_metric = np.nanmean(aps)
        else:
            self.num_inst[-1] = 1
            self.sum_metric[-1] = np.nanmean(aps)

    def _recall_prec(self):
        """ get recall and precision from internal records """
        n_fg_class = max(self._n_pos.keys()) + 1
        prec = [None] * n_fg_class
        rec = [None] * n_fg_class

        for l in self._n_pos.keys():
            score_l = np.array(self._score[l])
            match_l = np.array(self._match[l], dtype=np.int32)

            order = score_l.argsort()[::-1]
            match_l = match_l[order]

            tp = np.cumsum(match_l == 1)
            fp = np.cumsum(match_l == 0)

            # If an element of fp + tp is 0,
            # the corresponding element of prec[l] is nan.
            with np.errstate(divide='ignore', invalid='ignore'):
                prec[l] = tp / (fp + tp)
            # If n_pos[l] is 0, rec[l] is None.
            if self._n_pos[l] > 0:
                rec[l] = tp / self._n_pos[l]

        return rec, prec

    def _average_precision(self, rec, prec):
        """
        calculate average precision

        Params:
        ----------
        rec : numpy.array
            cumulated recall
        prec : numpy.array
            cumulated precision
        Returns:
        ----------
        ap as float
        """
        if rec is None or prec is None:
            return np.nan

        # append sentinel values at both ends
        mrec = np.concatenate(([0.], rec, [1.]))
        mpre = np.concatenate(([0.], np.nan_to_num(prec), [0.]))

        # compute precision integration ladder
        for i in range(mpre.size - 1, 0, -1):
            mpre[i - 1] = np.maximum(mpre[i - 1], mpre[i])

        # look for recall value changes
        i = np.where(mrec[1:] != mrec[:-1])[0]

        # sum (\delta recall) * prec
        ap = np.sum((mrec[i + 1] - mrec[i]) * mpre[i + 1])
        return ap


class New07PolygonMApMetric(NewPolygonMApMetric):
    """ Mean average precision metric for PASCAL V0C 07 dataset

    Parameters:
    ---------
    iou_thresh : float
        IOU overlap threshold for TP
    class_names : list of str
        optional, if provided, will print out AP for each class

    """
    def __init__(self, *args, **kwargs):
        super(New07PolygonMApMetric, self).__init__(*args, **kwargs)

    def _average_precision(self, rec, prec):
        """
        calculate average precision, override the default one,
        special 11-point metric

        Params:
        ----------
        rec : numpy.array
            cumulated recall
        prec : numpy.array
            cumulated precision
        Returns:
        ----------
        ap as float
        """
        if rec is None or prec is None:
            return np.nan
        ap = 0.
        for t in np.arange(0., 1.1, 0.1):
            if np.sum(rec >= t) == 0:
                p = 0
            else:
                p = np.max(np.nan_to_num(prec)[rec >= t])
            ap += p / 11.
        return ap
