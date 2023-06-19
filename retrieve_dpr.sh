MODEL_NAME=$1
EMBEDDING_PREFIX=$2
OUTPUT_FILE=$3
python dense_retriever.py \
	model_file=$MODEL_NAME \
	qa_dataset=nq_test \
	ctx_datatsets=[dpr_wiki] \
	encoded_ctx_files=[$EMBEDDING_PREFIX] \
	out_file=$OUTPUT_FILE \
	encoder=hf_bert_lastcat


# sample: bash retrieve_dpr.sh /mnt/cache/zhuty/DPR_output_models/bert_large/dpr_biencoder.30 "/mnt/cache/zhuty/DPR_output_embeddings/bert_large/shard*"  result_large.json
# sample: bash retrieve_dpr.sh /mnt/cache/zhuty/DPR_output_models/bert_base_expanded/dpr_biencoder.31  "/mnt/cache/zhuty/DPR_output_embeddings/bert_expanded/shard*"  result_expanded.json
# sample (for retrieving the inf dpr): bash retrieve_dpr.sh /mnt/cache/zhuty/DPR_output_models/bert_lastcat/dpr_biencoder.37  "/mnt/cache/zhuty/DPR_output_embeddings/bert_lastcat/shard*"  result_lastcat.json