import csv
import logging
import os
from typing import List, Optional

import numpy as np
import soundfile as sf
import torch

# import torchaudio
import torch.nn.functional as F
from omegaconf import DictConfig
from torch import Tensor as T

from dpr.data.biencoder_data import BiEncoderPassage, get_dpr_files, normalize_passage, JsonQADataset, JsonlQADataset
from dpr.data.retriever_data import QASrc, QASample
from dpr.utils.data_utils import read_data_from_json_files

logger = logging.getLogger(__name__)


class SpeechQASample(QASample):
    def __init__(self, query: T, id, answers: List[str], query_text: str = None):
        super().__init__(query, id, answers)
        self.query_text = query_text


class BiEncoderMixedSample(object):
    query: T
    positive_passages: List[BiEncoderPassage]
    negative_passages: List[BiEncoderPassage]
    hard_negative_passages: List[BiEncoderPassage]


class WavJsonTextDataset(JsonQADataset):
    def __init__(
        self,
        json_file: str,
        wav_tsv_file: str,
        selector: DictConfig = None,
        encoder_type: str = None,
        shuffle_positives: bool = False,
        normalize_text: bool = False,
        normalize_audio: bool = False,
        audio_file_prefix: str = "aud_dn_",
        max_features_sz: int = 100000,
    ):

        super().__init__(
            json_file,
            selector,
            encoder_type=encoder_type,
            shuffle_positives=shuffle_positives,
            normalize=normalize_text,
        )
        self.wav_tsv_file = wav_tsv_file
        self.audio_file_prefix = audio_file_prefix
        self.normalize_audio = normalize_audio
        self.id_to_audio_file_map = None
        self.max_features_sz = max_features_sz

        # tmp
        self.cut_samples = 0

    def load_data(self, start_pos: int = -1, end_pos: int = -1):
        super().load_data(start_pos=start_pos, end_pos=end_pos)
        self.id_to_audio_file_map = _get_id_to_audio_file_map(self.audio_file_prefix, self.wav_tsv_file)
        logger.info("id_to_audio_file_map  size: %d", len(self.id_to_audio_file_map))

    def __getitem__(self, index) -> BiEncoderMixedSample:
        json_sample = self.data[index]
        r = BiEncoderMixedSample()
        sample_id = index + 1
        audio_file = self.id_to_audio_file_map[sample_id]

        query_tensor = _get_audio_feats(audio_file, self.normalize_audio)

        if query_tensor.size(1) > self.max_features_sz:
            query_tensor = query_tensor[:, 0 : self.max_features_sz]
            self.cut_samples += 1
            if self.cut_samples % 100 == 0:
                logger.info("!!! cut_samples %d", self.cut_samples)

        # r.query = torchaudio.load(audio_file)
        r.query = query_tensor

        positive_ctxs = json_sample["positive_ctxs"]
        negative_ctxs = json_sample["negative_ctxs"] if "negative_ctxs" in json_sample else []
        hard_negative_ctxs = json_sample["hard_negative_ctxs"] if "hard_negative_ctxs" in json_sample else []

        for ctx in positive_ctxs + negative_ctxs + hard_negative_ctxs:
            if "title" not in ctx:
                ctx["title"] = None

        def create_passage(ctx: dict):
            return BiEncoderPassage(
                normalize_passage(ctx["text"]) if self.normalize else ctx["text"],
                ctx["title"],
            )

        r.positive_passages = [create_passage(ctx) for ctx in positive_ctxs]
        r.negative_passages = [create_passage(ctx) for ctx in negative_ctxs]
        r.hard_negative_passages = [create_passage(ctx) for ctx in hard_negative_ctxs]
        return r


# TODO: merge with WavJsonTextDataset
class WavPAQTextDataset(JsonlQADataset):
    def __init__(
        self,
        jsonl_file: str,
        manifest_txt_file: str,
        wav_root_dir: str,
        selector: DictConfig = None,
        encoder_type: str = None,
        shuffle_positives: bool = False,
        normalize_text: bool = False,
        normalize_audio: bool = False,
        audio_file_prefix: str = "aud_dn_",
        max_features_sz: int = 100000,
        total_data_size: int = -1,
    ):

        super().__init__(
            jsonl_file,
            selector,
            encoder_type=encoder_type,
            shuffle_positives=shuffle_positives,
            normalize=normalize_text,
            total_data_size=total_data_size,
        )
        self.manifest_txt_file = manifest_txt_file
        self.audio_file_prefix = audio_file_prefix
        self.normalize_audio = normalize_audio
        self.q_to_audio_file_map = None
        self.max_features_sz = max_features_sz
        self.wav_root_dir = wav_root_dir
        # tmp
        self.cut_samples = 0

    def load_data(self, start_pos: int = -1, end_pos: int = -1):
        if start_pos == -1:
            start_pos = 0
            end_pos = self.total_data_size

        super().load_data(start_pos=start_pos, end_pos=end_pos)
        # make q->wav file mapping
        questions = set()
        for json_sample in self.data:
            q = json_sample["question"]
            questions.add(q)
        logger.info("dataset questions num %d", len(questions))
        self.q_to_audio_file_map = _get_id_to_audio_file_map_paq(
            questions,
            self.wav_root_dir,
            self.audio_file_prefix,
            self.manifest_txt_file,
        )
        logger.info("q_to_audio_file_map %d", len(self.q_to_audio_file_map))

    def __getitem__(self, index) -> Optional[BiEncoderMixedSample]:
        json_sample = self.data[index]
        r = BiEncoderMixedSample()
        # sample_id = index
        q = json_sample["question"]
        if q not in self.q_to_audio_file_map:
            logger.warning("!!! sample with question=%s not in audio files dict ", q)
            return None
        audio_file = self.q_to_audio_file_map[q]

        query_tensor = _get_audio_feats(audio_file, self.normalize_audio)

        if query_tensor.size(1) > self.max_features_sz:
            query_tensor = query_tensor[:, 0 : self.max_features_sz]
            self.cut_samples += 1
            if self.cut_samples % 100 == 0:
                logger.info("!!! cut_samples %d", self.cut_samples)

        # r.query = torchaudio.load(audio_file)
        r.query = query_tensor

        positive_ctxs = json_sample["positive_ctxs"]
        negative_ctxs = json_sample["negative_ctxs"] if "negative_ctxs" in json_sample else []
        hard_negative_ctxs = json_sample["hard_negative_ctxs"] if "hard_negative_ctxs" in json_sample else []

        for ctx in positive_ctxs + negative_ctxs + hard_negative_ctxs:
            if "title" not in ctx:
                ctx["title"] = None

        def create_passage(ctx: dict):
            return BiEncoderPassage(
                normalize_passage(ctx["text"]) if self.normalize else ctx["text"],
                ctx["title"],
            )

        r.positive_passages = [create_passage(ctx) for ctx in positive_ctxs]
        r.negative_passages = [create_passage(ctx) for ctx in negative_ctxs]
        r.hard_negative_passages = [create_passage(ctx) for ctx in hard_negative_ctxs]
        return r


class QuantizedJsonTextDataset(JsonQADataset):
    def __init__(
        self,
        json_file: str,
        wav_tsv_file: str,
        km_file: str,
        max_audio_len: int,
        audio_file_prefix: str = "aud_dn_",
        quanized_token_prefix: str = "w2v",
        selector: DictConfig = None,
        encoder_type: str = None,
        shuffle_positives: bool = False,
        normalize_text: bool = False,
    ):
        super().__init__(
            json_file,
            selector,
            encoder_type=encoder_type,
            shuffle_positives=shuffle_positives,
            normalize=normalize_text,
        )
        self.wav_tsv_file = wav_tsv_file
        self.audio_file_prefix = audio_file_prefix
        self.km_file = km_file
        self.quanized_token_prefix = quanized_token_prefix
        self.id_to_audio_file_map = None
        self.max_audio_len = max_audio_len

        # tmp
        self.cut_samples = 0

    def load_data(self, start_pos: int = -1, end_pos: int = -1):

        orig_to_manifest_id_map = {}
        prefix_len = len(self.audio_file_prefix)
        suffix_len = len(".wav")
        logger.info("Reading audio manifest files: %s", self.wav_tsv_file)
        with open(os.path.join(self.wav_tsv_file), "r") as fp:  # read tsv file
            lines = fp.read().split("\n")
            lines.pop(0)
            manifest_id = 0
            for line in lines:
                if len(line) == 0:
                    continue
                file = line.split("\t")[0]
                orig_id = int(file[prefix_len:-suffix_len])
                assert orig_id not in orig_to_manifest_id_map
                orig_to_manifest_id_map[orig_id] = manifest_id
                manifest_id += 1
            logging.info("last manifest_id %d", manifest_id)
        logging.info("orig_to_manifest_id_map %d", len(orig_to_manifest_id_map))

        self.data_files = get_dpr_files(self.file)
        logger.info("Data files: %s", self.data_files)
        data = read_data_from_json_files(self.data_files)
        # filter those without positive ctx
        self.data = [r for r in data if len(r["positive_ctxs"]) > 0]
        logger.info("Total cleaned data size: {}".format(len(self.data)))

        # TODO:
        # if start_pos >= 0 and end_pos >= 0:
        #    logger.info("Selecting subset range from %d to %d", start_pos, end_pos)
        #    self.data = self.data[start_pos:end_pos]

        logger.info("Reading quantized audio files: %s", self.km_file)
        kms = []
        with open(self.km_file, "r") as ifile:
            reader = csv.reader(ifile, delimiter="\t")
            for i, row in enumerate(reader):
                assert len(row) == 1
                km_query_tokens = row[0].split()
                if len(km_query_tokens) > self.max_audio_len:
                    self.cut_samples += 1
                    km_query_tokens = km_query_tokens[0 : self.max_audio_len]
                kms.append(km_query_tokens)

        logging.info("Loaded quantized samples %d", len(kms))

        # inject quantized queries as string tokens to the main data
        assert len(data) == len(kms)
        for orig_id, sample in enumerate(data):
            manifest_id = orig_to_manifest_id_map[orig_id + 1]
            logging.debug("orig_id=%d manifest_id=%d", orig_id, manifest_id)
            km = kms[manifest_id]
            quanized_audio_q = ["[" + self.quanized_token_prefix + str(t) + "]" for t in km]
            quanized_audio_q = " ".join(quanized_audio_q)
            orig_q = sample["question"]
            sample["question"] = quanized_audio_q
            sample["orig_question"] = orig_q


class WavTextQADataset(QASrc):
    def __init__(
        self,
        file: str,
        wav_tsv_file: str,
        audio_file_prefix: str = "aud_dn_",
        max_features_sz: int = 100000,
        normalize_audio: bool = False,
        delim: str = "\t",
        question_pos: int = 0,
    ):
        super().__init__(file)
        self.wav_tsv_file = wav_tsv_file
        self.id_to_audio_file_map = {}
        self.audio_file_prefix = audio_file_prefix
        self.max_features_sz = max_features_sz
        self.normalize_audio = normalize_audio
        self.delim = delim

        # TODO: tmp
        self.length_buckets = {}

    def __getitem__(self, index) -> Optional[SpeechQASample]:
        sample = self.data[index]
        sample_id = index + 1
        audio_file = self.id_to_audio_file_map[sample_id]
        query_tensor = _get_audio_feats(audio_file, self.normalize_audio)

        # TODO: tmp
        size = query_tensor.size(1)
        bucket = int(size / 10000)
        cnt = self.length_buckets.get(bucket, 0)
        self.length_buckets[bucket] = cnt + 1

        if query_tensor.size(1) > self.max_features_sz:
            query_tensor = query_tensor[:, 0 : self.max_features_sz]

        sample.query = query_tensor
        return sample

    def __len__(self):
        return len(self.data)

    def load_data(self):
        super().load_data()
        data = []

        with open(self.file) as ifile:
            reader = csv.reader(ifile, delimiter=self.delim)
            for row in reader:
                question = row[0]
                answers = eval(row[1])
                data.append(SpeechQASample(None, None, answers, query_text=self._process_question(question)))

        self.data = data
        self.id_to_audio_file_map = _get_id_to_audio_file_map(self.audio_file_prefix, self.wav_tsv_file)
        logger.info("id_to_audio_file_map  size: %d", len(self.id_to_audio_file_map))


class SpeechReaderPreTrainingSample(object):
    """
    Container to collect all Q&A passages data per singe question
    """

    def __init__(
        self,
        audio: np.array,
        text_passages: List[str],
    ):
        self.audio = audio
        self.text_passages = text_passages


def _read_audio(fname):
    """Load an audio file and return PCM along with the sample rate"""
    wav, sr = sf.read(fname)
    assert sr == 16e3, f"File={fname}, sr={sr}"
    return wav


def _get_audio_feats(loc, normalize_audio: bool) -> T:
    x = _read_audio(loc)
    # logger.info("Raw Audio tensor %s, %s", x.shape, x)
    with torch.no_grad():
        source = torch.from_numpy(x).float()  # .cuda()
        if normalize_audio:
            assert source.dim() == 1, source.dim()
            with torch.no_grad():
                source = F.layer_norm(source, source.shape)
                # logger.info("Normalized Audio tensor %s, %s", source.size(), source)
        source = source.view(1, -1)
    return source


def _get_id_to_audio_file_map(audio_file_prefix: str, wav_tsv_file: str, delimiter: str = "\t"):
    id_to_file_map = {}
    prefix_len = len(audio_file_prefix)
    suffix_len = len(".wav")
    with open(wav_tsv_file, "r") as fp:  # read tsv file
        lines = fp.read().split("\n")
        root = lines.pop(0).strip()
        for line in lines:
            if len(line) == 0:
                continue
            file = line.split(delimiter)[0]
            id = int(file[prefix_len:-suffix_len])
            file_path = os.path.join(root, file)
            id_to_file_map[id] = file_path
    return id_to_file_map


def _get_id_to_audio_file_map_paq(
    questions: set,
    root: str,
    audio_file_prefix: str,
    wav_tsv_file: str,
    delimiter: str = "|",
):
    q_to_file_map = {}
    with open(wav_tsv_file, "r") as fp:  # read tsv file
        lines = fp.read().split("\n")
        for i, line in enumerate(lines):
            if len(line) == 0:
                continue
            sample = line.split(delimiter)
            q = sample[1]
            if q not in questions:
                continue
            id = sample[0]
            id_int = int(id)
            file_path = os.path.join(root, audio_file_prefix + id + ".wav")
            if not os.path.isfile(file_path):
                logger.warning("missing file audio %s", file_path)
            q_to_file_map[q] = file_path
    return q_to_file_map
