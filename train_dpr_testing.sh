export HYDRA_FULL_ERROR=1
python -m torch.distributed.launch --nproc_per_node=8 train_dense_encoder.py \
train=biencoder_nq_layer_extraction \
train_datasets=[nq_train] \
dev_datasets=[nq_dev] \
encoder=hf_bert_layer_extraction_12_3 \
output_dir=/home/aiops/zhuty/DPR_data/DPR_output_model/bert_base_layer_extraction_12_3

export HYDRA_FULL_ERROR=1
python -m torch.distributed.launch --nproc_per_node=8 train_dense_encoder.py \
train=biencoder_nq_layer_extraction \
train_datasets=[nq_train] \
dev_datasets=[nq_dev] \
encoder=hf_bert_layer_extraction_12_9 \
output_dir=/home/aiops/zhuty/DPR_data/DPR_output_model/bert_base_layer_extraction_12_9