python sbd_train_che_8_1.py --syncbn --network darknet53 --dataset coco \
--batch-size 32 --gpus 4,5  --num-workers 16 \
--warmup-epochs 4 --lr 0.0005 --epochs 201 --lr-decay 0.1  --lr-decay-epoch 160,180 \
--save-prefix ./result_coco_var_tanh_20_pretrain_ \
--resume result_coco_var_tanh_20_pretrain_yolo3_darknet53_coco_0010_0.0000.params --start-epoch 11 \
--lr-mode cosine --val_2012 True --label-smooth \
