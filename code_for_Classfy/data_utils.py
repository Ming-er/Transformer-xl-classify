import os, sys
import glob
from collections import Counter, OrderedDict
import numpy as np
import torch

from utils.vocabulary import Vocab


class BatchIteratorHelper:
    def __init__(self, data, lables, bsz, alianlen=3000, device='cpu'):
        '''

        :param data: [样本数，3000]
        :param lables: [样本数]
        :param bsz:  批次操作
        :param alianlen: 3000
        :param device:
        '''

        self.bsz = bsz
        self.num_example = data.size(0)   # 样本的个数
        self.device = device
        self.data = data.contiguous().to(device)
        # Number of mini-batches
        self.n_batch = (self.num_example + self.bsz - 1) // self.bsz  # 批次的个数
        self.lables = lables.contiguous().to(device)

        print(self.data.size())
        # 下面将进行验证
        assert self.data.size(1)==alianlen
        assert self.data.size(0)==self.lables.size(0)


    def get_batch(self, i, bsz=None):
        if bsz is None:
            bsz = self.bsz
        bsz_len = min(bsz, self.data.size(0) - 1 - i)
        end_idx = i + bsz_len
        beg_idx = i
        data = self.data[beg_idx:end_idx]

        labels=self.lables[beg_idx:end_idx]

        return data, labels,bsz_len

    def get_fixlen_iter(self, start=0):
        for i in range(start, self.data.size(0) - 1, self.bsz):
            yield self.get_batch(i)


    def __iter__(self):
        return self.get_fixlen_iter()




class LMOrderedIterator(object):
    def __init__(self, data, bsz, bptt, alianlen=3000, device='cpu', ext_len=None):
        '''
        :param data:
        :param bsz: batch_size
        :param bptt: tgt_len
        :param device:
        :param ext_len: 0
        '''
        """
            data -- LongTensor -- the LongTensor is strictly ordered
        """
        self.bsz = bsz
        self.bptt = bptt
        self.ext_len = ext_len if ext_len is not None else 0

        self.device = device

        # Work out how cleanly we can divide the dataset into bsz parts.
        # self.n_step = data.size(0) // bsz

        self.n_step = alianlen


        # # Trim off any extra elements that wouldn't cleanly fit (remainders).
        # data = data.narrow(0, 0, self.n_step * bsz)

        # Evenly divide the data across the bsz batches.
        self.data = data.t().contiguous().to(device)
        # print(self.data.size())
        # print(self.bsz)
        # print(self.n_step)
        # self.data = data.view(bsz, -1).t().contiguous().to(device)
        # Number of mini-batches
        self.n_batch = (self.n_step + self.bptt - 1) // self.bptt  #  这里不是一步一步的

        # 下面开始验证

        assert self.data.size(0)== self.n_step
        assert self.data.size(1) == self.bsz


    def get_batch(self, i, bptt=None):
        if bptt is None:
            bptt = self.bptt
        seq_len = min(bptt, self.data.size(0) - 1 - i)
        end_idx = i + seq_len
        beg_idx = max(0, i - self.ext_len)
        data = self.data[beg_idx:end_idx]

        return data, seq_len

    def get_fixlen_iter(self, start=0):
        for i in range(start, self.data.size(0) - 1, self.bptt):
            yield self.get_batch(i)

    def get_varlen_iter(self, start=0, std=5, min_len=5, max_deviation=3):
        max_len = self.bptt + max_deviation * std
        i = start
        while True:
            bptt = self.bptt if np.random.random() < 0.95 else self.bptt / 2.
            bptt = min(max_len, max(min_len, int(np.random.normal(bptt, std))))
            data, target, seq_len = self.get_batch(i, bptt)
            i += seq_len
            yield data, target, seq_len
            if i >= self.data.size(0) - 2:
                break

    def __iter__(self):
        return self.get_fixlen_iter()




# 许海明
class Corpus(object):
    def __init__(self, path, *args, **kwargs):
        self.vocab = Vocab(*args, **kwargs)

        # 从单词表里面加载单词
        self.vocab.build_vocab()

        # 训练集
        self.train       = self.vocab.encode_file( os.path.join(path, 'train.txt'), verbose=True)
        self.train_label = self.vocab.encode_file_only_for_lables(os.path.join(path, 'train.label'), verbose=True)

        # 验证集
        self.valid       = self.vocab.encode_file(os.path.join(path, 'valid.txt'), verbose=True)
        self.valid_label = self.vocab.encode_file_only_for_lables(os.path.join(path, 'valid.label'), verbose=True)


        # self.test = self.vocab.encode_file(
        #     os.path.join(path, 'test.txt'), ordered=True)

    # 许海明
    def get_batch_iterator(self, split, *args, **kwargs):
        '''

        :param split:
        :param args:
        :param kwargs:
        :return:
        '''
        if split == 'train':
            # data_iter = LMOrderedIterator(self.train, *args, **kwargs)
            batch_iter = BatchIteratorHelper(self.train,self.train_label, *args, **kwargs)

        elif split == 'valid':
            batch_iter = BatchIteratorHelper(self.valid, self.valid_label, *args, **kwargs)

        return batch_iter


def get_lm_corpus(datadir,vocab_file,alinlen):
    fn = os.path.join(datadir, 'cache.pt')
    if os.path.exists(fn):
        print('Loading cached dataset...')
        corpus = torch.load(fn)
    else:
        print('Producing dataset {}...'.format(datadir))
        kwargs = {}

        kwargs['special'] = ['<pad>','<s>', '<unk>', '</s>']
        kwargs['lower_case'] = False
        kwargs['vocab_file'] = vocab_file



        corpus = Corpus(datadir,alinlen ,**kwargs)
        torch.save(corpus, fn)  # 这里保存的是一个类的对象

    return corpus

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='unit test')
    parser.add_argument('--datadir', type=str, default='../data/enwik8',
                        help='location of the data corpus')
    parser.add_argument('--dataset', type=str, default='enwik8',
                        choices=['ptb', 'wt2', 'wt103', 'lm1b', 'enwik8', 'text8'],
                        help='dataset name')
    args = parser.parse_args()

    corpus = get_lm_corpus(args.datadir, args.dataset)
    print('Vocab size : {}'.format(len(corpus.vocab.idx2sym)))
    tr_iter = corpus.get_iterator('train', 22, 512)
    ##
    #  许海明 许海明  许海明  许海明 许海明
    #  许海明
    #
    #
    # ##
