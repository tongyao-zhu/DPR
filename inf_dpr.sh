MODEL_PATH=$1
OUT_PATH=$2
TOTAL_SHARD=$3
CURRENT_SHARD=$4
CUDA_VISIBLE_DEVICES=$CURRENT_SHARD python generate_dense_embeddings.py \
	model_file=$MODEL_PATH \
	ctx_src=dpr_wiki \
	shard_id=$CURRENT_SHARD num_shards=$TOTAL_SHARD \
	batch_size=256 \
	out_file=$OUT_PATH \
	encoder=hf_bert_lastcat

# sample: bash inf_dpr.sh /mnt/cache/zhuty/DPR_output_models/bert_large/dpr_biencoder.30 /mnt/cache/zhuty/DPR_output_embeddings/bert_large/shard  8 0
# bash inf_dpr.sh /mnt/cache/zhuty/DPR_output_models/bert_base_expanded/dpr_biencoder.31 /mnt/cache/zhuty/DPR_output_embeddings/bert_expanded/shard  8 0
# conda activate dpr_env ; bash inf_dpr.sh /mnt/cache/zhuty/DPR_output_models/bert_lastcat/dpr_biencoder.37 /mnt/cache/zhuty/DPR_output_embeddings/bert_lastcat/shard  8 0