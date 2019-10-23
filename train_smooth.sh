python sbd_train_che_8_1.py --syncbn --network darknet53 --dataset voc \
--batch-size 64 --gpus 0,1 --num-workers 16 \
--warmup-epochs 4 --lr 0.0003 --epochs 201 --lr-decay 0.1  --lr-decay-epoch 160,180 \
--save-prefix ./darknet53_result_pretrain_cosine_val2012_uniform_smooth_ \
--resume darknet53_pretrain_yolo3_darknet53_coco_pretrain_0020_0.0000.params --start-epoch 0 \
--lr-mode cosine --val_2012 True --label-smooth