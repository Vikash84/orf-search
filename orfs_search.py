#!/usr/bin/env python3
import sys
import os
from os.path import isfile, isdir, join
import tempfile

import logging

import subprocess
import resource

import argparse
import yaml

execution_path = os.path.dirname(os.path.abspath(__file__))

def align_hmms(hmms_file, graph_file, k, evalue, threads, out_dir):
    com = execution_path + "/aligners/pathracer " + hmms_file + " " + graph_file + " " + str(k) \
        + " --output " + out_dir + " --rescore --annotate-graph --threads " + str(threads) \
        + " -E " + evalue + " --domE " + evalue + " --max-size 500000 > " + out_dir + ".log"
    logging.info( u'Running: ' + com)
    return_code = subprocess.call([com], shell=True)
    return out_dir, return_code

def align_sequences(graph_file, k, protein_file, threads, out_prefix):
    com = execution_path + "/aligners/spaligner " + execution_path + "/aligners/spaligner_cfg.yaml -g " + graph_file + \
                    " -k " + str(k) + " -s " + protein_file + " -t " + str(threads) + \
                     " -d protein -o " + out_prefix + " > " + out_prefix + ".log"
    logging.info( u'Running: ' + com)
    return_code = subprocess.call([com], shell=True)
    return out_prefix + "/alignment.fasta", return_code

def find_true_hmm_alignments(hmmer_path, proteins_file, hmms_file, evalue, threads, out_file):
    com = hmmer_path + "hmmsearch --domtblout " + out_file + \
                    ".dtbl -E " + evalue + " --cpu " + str(threads)  + " " + hmms_file + " " + proteins_file \
                    + " > " + out_file + "_true.log"
    logging.info( u'Running: ' + com)
    return_code = subprocess.call([com], shell=True)
    return out_file + ".dtbl", return_code

def extract_ORFs_from_graph(hmms_alignments, proteins_alignments, graph_file, k, proteins_file, \
                            hmms_true_alignments, longestorf, threads, out_file, out_dir):
    com = execution_path + "/scripts/identify_gene_ends.py "
    if os.path.exists(proteins_alignments):
        com += "-s " + proteins_alignments
    if os.path.exists(hmms_alignments):
        com += " -m " + hmms_alignments + \
               " -p " + proteins_file + \
               " -d " + hmms_true_alignments
    if longestorf:
        com += " -f "
    com += " -g " + graph_file + " -k " + str(k) + " -t " + str(threads) +" -o " + out_file
    logging.info( u'Running: ' + com)
    return_code = subprocess.call([com], shell=True)
    return out_file + ".fasta", return_code

def filter_orfs(orfs_sequences, graph, proteins_file, contigs_file, threads, print_all, out_file, out_dir):

    com = execution_path + "/scripts/filter_ORFs.py -s " + orfs_sequences + \
                        " -g " + graph + " -t " + str(threads) + " -o " + out_file
    if not print_all:
        if contigs_file != None:
            com += " -c " + contigs_file
        com += " -p " + proteins_file
    logging.info( u'Running: ' + com)
    return_code = subprocess.call([com], shell=True)
    return out_file + ".fasta", return_code

def load_yaml():
    p = os.path.abspath(__file__)
    with open(p[:-len("orfs_search.py")] + "/config.yaml", 'r') as stream:
        try:
            res = yaml.load(stream)
        except yaml.YAMLError as exc:
            logging.error(exc)
            exit(-1)
    return res["hmmer_path"], res["pathracer"]["evalue"]


def main(args):
    parser = argparse.ArgumentParser(description='Searches for potential genes in assembly graphs')
    parser.add_argument('-m', '--hmms', help='file with hmms in HMMer format', required=True)
    parser.add_argument('-s', '--sequences', help='fasta-file with proteins(optional)', required=False)
    parser.add_argument('-r', '--runspaligner', help='if set, run SPAligner on proteins', action='store_true')
    parser.add_argument('-g', '--graph', help='assembly graph in gfa-format', required=True)
    parser.add_argument('-k', '--kmer', help='assembly graph k-mer size', required=True)
    parser.add_argument('-c', '--contigs', help='fasta-file with assembly contigs', required=False)
    parser.add_argument('-f', '--longestorf', help='generate ORFs that have stop codon before start codon', action='store_true')
    parser.add_argument('-t', '--threads', help='number of threads', required=False)
    parser.add_argument('-a', '--all', help='do not perform filtering based on contigs or known IPGs', required=False, action='store_true')
    parser.add_argument('-o', '--out', help='output directory', required=True)
    is_test = False
    if len(args) == 2 and args[1] == "--test":
        is_test = True
        tmp_dir = tempfile.TemporaryDirectory()
        p = os.path.abspath(__file__)
        args = [args[0], "-m", p[:-len("orfs_search.py")]  + "/tiny_dataset/ricinb_lectin2.hmm", "-s", p[:-len("orfs_search.py")] + "/tiny_dataset/toxin.fasta", \
                         "-r", "-g", p[:-len("orfs_search.py")]  + "/tiny_dataset/graph.gfa", "-k", "55", "-o", tmp_dir.name]
    args = parser.parse_args(args[1:])

    logging.basicConfig(format = u'%(levelname)-8s [%(asctime)s] %(message)s', level = logging.DEBUG)
    logging.basicConfig(format = u'%(levelname)-8s [%(asctime)s] %(message)s', level = logging.DEBUG, filename = args.out + u'orfs_search.log')

    if is_test:
        logging.info(u'Start test on a small dataset...')

    hmmer_path, evalue= load_yaml()
    if hmmer_path == None:
        hmmer_path = ""

    if not os.path.exists(args.out):
        os.makedirs(args.out)

    t = 1
    if args.threads != None:
        t = int(args.threads)

    hmms_name = ".".join(args.hmms.split("/")[-1].split(".")[0:-1])
    hmm_return_str, hmm_return_code = align_hmms(args.hmms, args.graph, args.kmer, str(evalue), min(t, 16), join(args.out, hmms_name))
    if hmm_return_code != 0:
        logging.warning( u'HMM alignment failed')
    if hmm_return_code == 0 and args.sequences != None and not os.path.exists(join(args.out, hmms_name + ".dtbl")):
        find_true_hmm_alignments(hmmer_path, args.sequences, args.hmms, str(evalue), t, join(args.out, hmms_name))

    if args.sequences != None and args.runspaligner:
        seq_name = args.sequences.split("/")[-1].split(".")[0]
        seq_return_str, seq_return_code = align_sequences(args.graph, args.kmer, args.sequences, t, join(args.out, seq_name))
        if seq_return_code != 0:
            logging.warning( u'Sequence alignment failed')
    else:
        seq_return_str = ""
        seq_return_code = 0

    if seq_return_code != 0 and hmm_return_code != 0:
        logging.error( u'No data was generated to find orfs')
        exit(-1)

    orfs_fasta, return_code = extract_ORFs_from_graph(hmm_return_str, seq_return_str, args.graph, args.kmer, \
                                                        args.sequences, join(args.out, hmms_name + ".dtbl"), \
                                                        args.longestorf, t, join(args.out, "orfs_raw"), args.out)

    if return_code != 0:
        logging.error( u'Orfs generation failed')
        exit(-1)

    final_orfs_str, return_code = filter_orfs(orfs_fasta, args.graph, args.sequences, args.contigs, t, args.all, join(args.out, "orfs_final"), args.out)
    if return_code != 0:
        logging.error( u'Filtering failed')
        exit(-1)

    logging.info( u'ORFs search finished. Please find results here: ' + args.out + "/")

    if is_test:
        logging.info(u'The test finished successfully!')
        tmp_dir.cleanup()



if __name__ == "__main__":
    main(sys.argv)