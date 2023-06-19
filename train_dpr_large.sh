python -m torch.distributed.launch --nproc_per_node=8 train_dense_encoder.py \
train=biencoder_nq_large \
train_datasets=[nq_train] \
dev_datasets=[nq_dev] \
encoder=hf_bert_large \
output_dir=/mnt/cache/zhuty/DPR_output_models/bert_large
