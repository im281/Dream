#!/usr/bin/env python

from __future__ import print_function

import re
import os
import yaml
import shutil
import argparse
import subprocess
import traceback
import tempfile
import synapseclient
import sys
import json
import getpass
from sys import argv

DREAM_RNA_BUCKET = "gs://dream-smc-rna"

REFERENCE_DATA = {
    "REFERENCE_GENOME" : "Homo_sapiens.GRCh37.75.dna_sm.primary_assembly.fa",
    "REFERENCE_GTF" : "Homo_sapiens.GRCh37.75.gtf"
}

FILE_SUFFIX = ["_filtered.bedpe", "_isoforms_truth.txt", "_mergeSort_1.fq.gz", "_mergeSort_2.fq.gz"]

def synapse_login():
    try:
        syn = synapseclient.login()
    except Exception as e:
        print("Please provide your synapse username/email and password (You will only be prompted once)")
        Username = raw_input("Username: ")
        Password = getpass.getpass()
        syn = synapseclient.login(email=Username, password=Password,rememberMe=True)
    return syn

def validate_cwl(cwlpath):
    try:
        test = subprocess.check_call(['cwltool', '--print-pre', cwlpath])
    except Exception as e:
        raise ValueError('Your CWL file is not formatted correctly', e)

def load_cwl(cwlpath):
    with open(cwlpath, 'r') as cwlfile:
        try:
            cwl = yaml.load(cwlfile)
        except Exception as e:
            raise Exception('Must be a CWL file (YAML format)')

    return cwl


def find_synapse_data(cwl):
    input = filter(lambda input: input.get('class', None) == "Workflow", cwl['$graph'])[0]
    return input['hints'][0]['entity']

def call_cwl(tool, inputs, nocache=False, cachedir = "cwl-cache"):
    if nocache:
        arguments = ["cwl-runner",tool]
    else:
        arguments = ["cwl-runner",
                     "--cachedir", cachedir,
                     tool]
    arguments.extend(inputs)
    try:
        print("Running: %s" % (" ".join(arguments)))
        process = subprocess.Popen(arguments, stdout=subprocess.PIPE)
        output, error = process.communicate()
        temp = json.loads(output)
        print(temp)
        return(temp['OUTPUT']['path'])
    except Exception as e:
        traceback.print_exc()
        print("Unable to call cwltool")
    #return(temp['output']['path'])

def call_workflow(cwl, fastq1, fastq2, index_path, nocache=False, cachedir="cwl-cache"):
    inputs = ["--index", index_path,
              "--TUMOR_FASTQ_1", fastq1,
              "--TUMOR_FASTQ_2", fastq2]

    output = call_cwl(cwl, inputs, nocache, cachedir)
    return(output)

def call_evaluation(cwl, workflow_output, truth, annotations, nocache=False, cachedir="cwl-cache"):
    # local = "eval-workflow.cwl"
    # shutil.copyfile(cwl, local)
    inputs = ["--input", workflow_output,
              "--truth", truth]
    if annotations is not None:
        inputs.extend(["--gtf", annotations])

    call_cwl(cwl, inputs, nocache, cachedir)
    # os.remove(local)

def run_dream(synapse, args):
    cwlpath = args.workflow_cwl
    validate_cwl(cwlpath)
    cwl = load_cwl(cwlpath)
    synapse_id = find_synapse_data(cwl)

    print("SYNAPSE: " + synapse_id)

    # index = synapse.get(synapse_id, downloadLocation="/data")
    index = synapse.get(synapse_id)
    workflow_out = call_workflow(args.workflow_cwl, args.fastq1, args.fastq2, index.path)
    call_evaluation(args.eval_cwl, workflow_out, args.truth, args.annotations)

def download(synapse,args):
    try:
        subprocess.check_call(["gsutil", "ls" ,DREAM_RNA_BUCKET])
    except Exception as e:
        raise ValueError("You are not logged in to gcloud.  Please login by doing 'gcloud auth login' and follow the steps to have access to the google bucket")
    print("Caching Inputs files", file=sys.stderr)
    for suf in FILE_SUFFIX:
        local_path = os.path.join(args.dir, args.input + suf)
        if not os.path.exists(local_path):
            if args.input.startswith("sim"):
                data = "%s/training/%s_*" % (DREAM_RNA_BUCKET, args.input)
            elif args.input.startswith("dryrun"):
                data = "%s/debugging/%s_*" % (DREAM_RNA_BUCKET, args.input)                    
            cmd = ["gsutil","cp", data, args.dir]
            subprocess.check_call(cmd)

def gen_inputs(syn,args):
    with open(args.workflow) as handle:
        doc = yaml.load(handle.read())
    custom_inputs = {}
    for hint in doc.get("hints", []):
        if 'synData' == hint.get("class", ""):
            ent = syn.get(hint['entity'])
            custom_inputs[hint['input']] = {
                "class" : "File",
                "path" : ent.path
            }
    download(syn, args)
    in_req = {
        "TUMOR_FASTQ_1" : {
            "class" : "File",
            "path" : os.path.abspath(os.path.join(args.dir, args.input + "_mergeSort_1.fq.gz"))
        },
        "TUMOR_FASTQ_2" : {
            "class" : "File",
            "path" : os.path.abspath(os.path.join(args.dir, args.input + "_mergeSort_2.fq.gz"))
        }
    }
    for k, v in REFERENCE_DATA.items():
        in_req[k] = {
            "class" : "File",
            "path" : os.path.abspath(os.path.join(args.dir, v))
        }
    for k, v in custom_inputs.items():
        in_req[k] = v
    return in_req

def run_test(syn,args):
    try:
        subprocess.check_call(["gsutil", "ls" ,DREAM_RNA_BUCKET])
    except Exception as e:
        raise ValueError("You are not logged in to gcloud.  Please login by doing 'gcloud auth login' and follow the steps to have access to the google bucket")
    if not os.path.exists(args.dir):
        print("Making directory %s" % args.dir, file=sys.stderr)
        os.mkdir(args.dir)

    for ref in REFERENCE_DATA.values():
        if not os.path.exists(os.path.join(args.dir, ref)):
            cmd = ["gsutil", "cp", "%s/%s.gz" % (DREAM_RNA_BUCKET, ref), args.dir]
            subprocess.check_call(cmd)
            cmd = ["gunzip", os.path.join(args.dir, "%s.gz" % (ref))]
            subprocess.check_call(cmd)
        
    in_req = gen_inputs(syn,args)
    print(json.dumps(in_req, indent=4))
        
    tmp = tempfile.NamedTemporaryFile(dir=args.dir, prefix="dream_runner_input_", suffix=".json", delete=False)
    tmp.write(json.dumps(in_req))
    tmp.close()
    workflow_out = call_cwl(args.workflow, [tmp.name], args.no_cache, cachedir=args.cachedir)
    if args.challenge == "fusion":
        cwl = os.path.join(os.path.dirname(__file__),"..","FusionDetection","cwl","FusionEvalWorkflow.cwl")
        truth = os.path.abspath(os.path.join(args.dir, args.input + "_filtered.bedpe"))
        annots = syn.get("syn5908245")
        annotations = annots.path
        call_evaluation(cwl, workflow_out, truth, annotations, args.no_cache, cachedir=args.cachedir)
    #elif args.challenge == "fusionQuant":
        cwl = os.path.join(os.path.dirname(__file__),"..","FusionQuantification","cwl","FusionQuantWorkflow.cwl")
        truth = os.path.abspath(os.path.join(args.dir, args.input + "_filtered.bedpe"))
        annots = syn.get("syn5908245")
        annotations = None
    elif args.challenge == "isoform":
        cwl = os.path.join(os.path.dirname(__file__),"..","IsoformQuantification","cwl","QuantificationEvalWorkflow.cwl")
        truth = os.path.abspath(os.path.join(args.dir, args.input + "_isoforms_truth.txt"))
        annotations = os.path.abspath(os.path.join(args.dir, "Homo_sapiens.GRCh37.75.gtf"))
    else:
        raise ValueError("Please pick either 'fusion' or 'isoform' for challenges")
    call_evaluation(cwl, workflow_out, truth, annotations, args.no_cache, cachedir=args.cachedir)

def run_inputs(syn,args):
    in_req = gen_inputs(syn,args)
    print(json.dumps(in_req, indent=4))

def run_list(syn,args):
    cmd = ["gsutil", "ls", "%s/training/*.fq.gz" % (DREAM_RNA_BUCKET)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    out = []
    for line in stdout.split("\n"):
        if line.startswith("gs://"):
            res = re.search(r'(sim.*)_merge', line)
            if res:
                if res.group(1) not in out:
                    out.append(res.group(1))
    print("\n".join(out))

def perform_main(args):
    synapse = synapse_login()
    if 'func' in args:
        try:
            args.func(synapse,args)
        except Exception as ex:
            print(traceback.print_exc())
            print(ex)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='DREAM runner - run your workflow from beginning to end.')
    
    subparsers = parser.add_subparsers(title='commands',description='The following commands are available:')
    
    parser_run = subparsers.add_parser('run',help='Runs workflow and evaluation framework')
    parser_run.add_argument('--workflow-cwl',  default='smc-tophat-workflow.cwl', type=str, help='cwl workflow file')
    parser_run.add_argument('--eval-cwl',  default='eval-workflow.cwl', type=str, help='cwl workflow file')
    parser_run.add_argument('--fastq1', default='sim1a_30m_merged_1.fq.gz')
    parser_run.add_argument('--fastq2', default='sim1a_30m_merged_2.fq.gz')
    parser_run.add_argument('--truth', default='truth.bedpe')
    parser_run.add_argument('--annotations', default='ensembl.hg19.txt')
    parser_run.add_argument('--bucket', default="gs://dream-smc-rna")
    parser_run.set_defaults(func=run_dream)
    
    parser_download = subparsers.add_parser('download',help='Downloads training and dry-run data')
    parser_download.add_argument('input', type=str,
        help='download training or dry data')
    parser_download.add_argument('--dir', default="./", type=str, 
        help='Directory to download files to')
    parser_download.add_argument('--bucket', default="gs://dream-smc-rna")
    parser_download.set_defaults(func=download)
    
    parser_test = subparsers.add_parser('test',help='Downloads training and dry-run data')
    parser_test.add_argument("--dir", type=str, default="./",
        help='Directory to download data to')
    parser_test.add_argument("input", type = str,
        help='Training/debugging dataset to use')
    parser_test.add_argument("workflow", type = str,
        help='Non merged workflow file')
    parser_test.add_argument("challenge", type = str,
        help='Choose the challenge question: fusion or isoform')
    parser_test.add_argument("--no-cache", action='store_true',
        help='Do not cache workflow steps')
    parser_test.add_argument("--cachedir", type=str, default="cwl-cache",
        help='Directory to cache cwl run')
    parser_test.add_argument('--bucket', default="gs://dream-smc-rna")
    parser_test.set_defaults(func=run_test)

    parser_inputs = subparsers.add_parser('inputs',help='Create Input JSON')
    parser_inputs.add_argument("--dir", type=str, default="./",
        help='Directory to download data to')
    parser_inputs.add_argument("input", type = str,
        help='Training/debugging dataset to use' )
    parser_inputs.add_argument("workflow", type = str,
        help='Non merged workflow file')
    parser_inputs.add_argument("challenge", type = str,
        help='Choose the challenge question: fusion or isoform')
    parser_inputs.add_argument("--no-cache", action='store_true',
        help='Do not cache workflow steps')
    parser_inputs.add_argument("--cachedir", type=str, default="cwl-cache",
        help='Directory to cache cwl run')
    parser_inputs.add_argument('--bucket', default="gs://dream-smc-rna")
    parser_inputs.set_defaults(func=run_inputs)
    
    parser_list = subparsers.add_parser('list',help='List Avalible tumors')
    parser_list.add_argument('--bucket', default="gs://dream-smc-rna")
    parser_list.set_defaults(func=run_list)


    args = parser.parse_args()
    
    DREAM_RNA_BUCKET = args.bucket
    
    perform_main(args)