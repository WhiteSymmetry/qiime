#!/usr/bin/env python
#file exclude_seqs_by_blast.py
from __future__ import division
from time import strftime, time
from optparse import OptionParser
from sets import Set
from os import system
from cogent.parse.fasta import MinimalFastaParser
from cogent.app.blast import blast_seqs, Blastall, BlastResult


__author__ = "Jesse Zaneveld"
__copyright__ = "Copyright 2009, the PyCogent Project"
__credits__ = ["Jesse Zaneveld","Rob Knight"]
__license__ = "GPL"
__version__ = "0.1"
__maintainer__ = "Jesse Zaneveld"
__email__ = "zaneveld@gmail.com"
__status__ = "Prototype"




"""
A lightweight script for BLASTing one or more sequences against a number of BLAST databases, and returning FASTA files a) of the results that did match b) of the results that didn't match c) raw blast results and also d) returning a report containing the parameters used, which sequences were excluded and why.
"""

FORMAT_BAR =   """------------------------------"""*2


def blast_genome(seqs,blast_db,e_value,max_hits, word_size, working_dir,\
                  blast_mat_root, extra_params=[],DEBUG=True):
    """Blast sequences against all genes in a genome"""
    
    # set up params to use with blastp or 
    params = {
        # matrix
        "-M":"BLOSUM62",

        # max procs
        "-a":"1",

        # expectation
        "-e":e_value,

        # max seqs to show
        "-b":max_hits,
        
        # Word size
        "-W":word_size,

        # max one line descriptions
        "-v":max_hits,
        
        #tabular output
        "-m":"9",

        # program
        "-p":"blastn"
    }
    params.update(extra_params)

    output=blast_seqs(seqs,\
                Blastall,\
                blast_db=blast_db,\
                params=params,\
                WorkingDir=working_dir,\
                add_seq_names=False,\
                blast_mat_root=blast_mat_root)
    
    raw_output=[x for x in output['StdOut']]
    return raw_output
   

def find_homologs(query_file,subject_genome,e_value,max_hits,\
            working_dir,blast_mat_root,wordsize,\
                             percent_aligned,extra_params={},\
                               require_hit=False,DEBUG=True):
    """BLAST query_file against subject_genome
    
    query_file -- .nuc file or other FASTA file to BLAST against all files in file_list
    
    subject_genome -- path to a KEGG .nuc file or other FASTA formated file. 

    e-value -- e-value threshold for blasts
   
    percent_aligned -- minumum percent alignment, between 0.0 and 1.0 

    max_hits,blast_mat_root,extra_params -- these are passed along to blastn

    DEBUG -- if True, display debugging output
    """     
    start_time=time()
    raw_blast_output=[]
    seqs=open(query_file,"U").readlines()
    subj_seqs=open(subject_genome,"U").readlines()
    
    if DEBUG:
        print "BLASTING %s vs. %s" %(query_file,subject_genome)
    
    blast_db=subject_genome
        
    raw_output_data=blast_genome(seqs,\
                     blast_db,e_value,\
                 max_hits,wordsize,working_dir,\
          blast_mat_root,extra_params,\
                           DEBUG=DEBUG)
    
    
    if DEBUG:
        print "Length of raw BLAST results:", len(raw_output_data)
    
    
    curr_blast_result=BlastResult(raw_output_data)
     
    align_filter = make_percent_align_filter(percent_aligned)
    #should a mismatch filter be added?
    
    filtered_ids, removed_ids=query_ids_from_blast_result(curr_blast_result,
                                                     align_filter, DEBUG=DEBUG)
            
    return raw_output_data, filtered_ids, removed_ids

def sequences_to_file(results,outfile_name):
    """Translate a generator of label,seq tuples to an output file """
    
    f=open(outfile_name,'w+')
    for label,seq in results:
        output_lines=[]
        output_lines.append(">%s\n" % label)
        output_lines.append("%s\n" % seq)
        f.writelines(output_lines)
    f.close()

def no_filter(blast_subject_entry):
    """A placeholder filter function which always returns True"""
    return True

def make_percent_align_filter(min_percent):
    """Return a filter function that filters BLAST results on % alignment
    min_percent -- minimum percent match as a float between 0 and 1"""
    min_percent = float(min_percent) * 100
    
    def align_filter(blast_result):
        if float(blast_result['% IDENTITY']) < min_percent:
            return False
        else:
            return True
    
    return align_filter

def check_align_percent_field(d):
    """Check for empty percent identity fields in a dict"""
    if d['% IDENTITY']:
        return True
    else:
        return False

def query_ids_from_blast_result(blast_result,filter_fn=no_filter,DEBUG=False):
    """Returns a list of blast query ids, filtered by a given function.
        
        --blast_result:  BLAST result from BLAST app controller
        
        --filter_fn:  a function that, given a dict representing a BLAST result
                      returns True or False based on whether the result passes
                      some filter.
    """
    ok_ids=[]
    removed_ids=[]
    for id in blast_result:
        for entry in blast_result[id]:
            for subentry in entry:
                if not check_align_percent_field(subentry):
                    continue
                if not filter_fn(subentry):
                    removed_ids.append(id)
                    continue
                ok_ids.append(subentry['QUERY ID'])
    ok_ids = set(ok_ids)
    
    #Ensure query seqs with multiple BLAST hits, only some of which 
    #are filtered out, don't end up in removed_ids
    
    removed_ids = set(removed_ids) - ok_ids 
    return ok_ids, removed_ids

def ids_from_fasta_lines(lines):
    """Extract ids from label lines"""
    ids = [] 
    for line in lines:
        if not line.startswith(">"):
            continue
        id= id_from_fasta_label_line(line) 
        ids.append(id)

    return ids

def id_from_fasta_label_line(line):
    "Extract id from fasta label line"
    id_field = line.split()[0]
    id = id_field.strip(">")
    return id

def seqs_from_file(ids,file_lines):
    """Extract labels and seqs from file"""

    for label, seq in MinimalFastaParser(file_lines):
    
        if id_from_fasta_label_line(label) in ids:
            yield label,seq

def compose_logfile_lines(start_time,db_format_time,blast_time,option_lines,\
                                 formatdb_cmd,blast_results,options,all_ids,\
                                                    hit_ids,removed_hit_ids,\
                                                       included_ids, DEBUG):
    """Compose lines for a logfile from data on analysis"""

    log_lines =[]
    log_lines.append("Sequence exclusion analysis run on %s" % strftime("%c"))
    log_lines.append("Formatting subject database took  %2.f seconds" % (db_format_time)) 
    log_lines.append("BLAST search took  %2.f minute(s)" % ((blast_time)/60.0)) 
    log_lines.append("Total analysis completed in %2.f minute(s)" % ((time() - start_time)/60.0)) 
    
    
    log_lines.append(FORMAT_BAR)
    log_lines.append("|                      Options                             |")
    log_lines.append(FORMAT_BAR)
    
    log_lines.extend(option_lines)
    log_lines.append("Subject database formatted with command: %s" \
                                                      %formatdb_cmd)
    
    log_lines.append(FORMAT_BAR)
    log_lines.append("|                      Results                             |")
    log_lines.append(FORMAT_BAR)
    
    log_lines.append("BLAST results above e-value threshold:")
    log_lines.append("\t".join(["Query id", "Subject id", "percent identity", "alignment length",\
                 "mismatches", "gap openings", "q. start","q. end", "s. start","s. end", "e-value", "bit score"]))

    for line in blast_results:
        if line.startswith("#"):
            continue
        else:
            log_lines.append(line)

    log_lines.append("Hits matching e-value and percent alignment filter: %s" % ','.join(sorted(hit_ids))) 
    
    log_lines.append(FORMAT_BAR)
    log_lines.append("|                      Summary                             |")
    log_lines.append(FORMAT_BAR)

    log_lines.append("Input query sequences: %i" % len(all_ids))
    log_lines.append("Query hits from BLAST: %i" % (len(hit_ids)+len(removed_hit_ids)))
    log_lines.append("Query hits from BLAST lacking minimal percent alignment: %i" % len(removed_hit_ids))
    log_lines.append("Final hits: %i" % len(hit_ids))
    log_lines.append("Output screened sequences: %i" % len(included_ids))
    
    log_lines.append(FORMAT_BAR)
    log_lines.append("|                       Output                             |")
    log_lines.append(FORMAT_BAR)

    log_lines.append("Writing excluded sequences (hits matching filters) to: %s" %options.outputfilename + '.excluded') 
    log_lines.append("Writing screened sequences (excluding hits matching filters) to: %s" %options.outputfilename + '.screened') 
    log_lines.append("Writing raw BLAST results to: %s" %options.outputfilename + '.raw_blast_results') 
    
    #format for printing
    revised_log_lines=[]
    for line in log_lines:
        line = line + "\n"
        revised_log_lines.append(line)
    
    if DEBUG:
        for line in log_lines:
            print line
    
    return revised_log_lines 

def make_option_parser():
    """Generate a parser for command-line options"""
    
    description= """ 
    This script is designed to aide in the removal of human sequence 
contaminants from sequencing runs. Sequences from the run are searched 
against a user-specified subject database. Hits are screened by e-value 
and the percentage of the query that aligns to the sequence. Four output 
files are generated based on the supplied outputpath + unique suffixes:  
a FASTA file of sequences that passed the screen,
a FASTA file of sequences that did not pass the screen (i.e. 
matched the database and passed all filters), the raw BLAST results from the
screen and a log file summarizing the options used and results obtained. A copy of human nucleotide 
sequences useful for excluding human genomic contamination from sequencing runs 
can be found at:  ftp://ftp.genome.jp/pub/kegg/genes/organisms/hsa/h.sapiens.nuc
"""
    usage = """\n\tpython exclude_seqs_by_blast.py [options]\n\nExample:\n\tpython exclude_seqs_by_blast.py -i /Users/zaneveld/test_query_data.fasta -d /Users/zaneveld/data/h.sapiens.nuc -e 1e-20 -p 0.97 -f ./pos1_control_test --debug"""

    parser=OptionParser(usage=usage,description=description)
    parser.add_option("-i","--querydb",dest='querydb',default = None,\
        help="REQUIRED: The path to a FASTA file containing query sequences")
    parser.add_option("-d","--subjectdb",dest='subjectdb',default = None,\
        help="REQUIRED: The path to a FASTA file to BLAST against")
    parser.add_option("-f","--outputfilename",dest='outputfilename',\
        default = None,\
        help="""REQUIRED: The base path/filename to save results.  Sequences passing the screen, failing the screen, raw BLAST results and the log will be saved to your filename + '.screened', '.excluded', '.raw_blast_results', and '.sequence_exclusion_log' respectively.""")
    parser.add_option("-e","--e_value",type='float',dest='e_value',\
        default = 1e-10,\
        help="The e-value cutoff for blast queries [DEFAULT: %default]")
    parser.add_option("-p","--percent_aligned",type='float',\
        dest='percent_aligned',default = 0.97,\
        help="The %% alignment cutoff for blast queries [DEFAULT: %default]")
    parser.add_option("--blastmatroot",dest='blastmatroot',default = None,\
            help="Path to a folder containing blast matrices. [DEFAULT: %default]")
    parser.add_option("--working_dir",dest='working_dir',default = "/tmp",\
        help="Working dir for BLAST [DEFAULT: %default]")
    parser.add_option("-M","--max_hits",type='int',dest='max_hits',\
        default = 100,\
        help="Max hits parameter for BLAST.  CAUTION: Because filtering on alignment percentage occurs after BLAST, a max hits value of 1 in combination with an alignment percent filter could miss valid contaminants. [DEFAULT: %default] ")
    parser.add_option("-W","--word_size",type='int',dest='wordsize',\
        default = 28,\
        help="Word size to use for BLAST search [DEFAULT: %default]")
    parser.add_option("--debug",action='store_true',dest='debug',\
        default = False,\
        help="If present, display verbose debugging output [DEFAULT: %default]")
    return parser

def check_options(parser,options):
    """Check to insure required options have been supplied"""
    if options.percent_aligned > 1.0:
        parser.error(\
            "Please check -p option: should be between 0.0(0%) and 1.0(100%)")
    
    if options.querydb is None:
        parser.error(\
                "Please check -i option: must specify path to a FASTA file")  
    try:
        f=open(options.querydb,'r')
        f.close()
    except IOError:
        parser.error(\
                "Please check -i option: cannot read from query FASTA filepath")  
    if options.subjectdb is None:
        parser.error(\
                "Please check -d option: must specify path to a FASTA file")  
    try:
        f=open(options.subjectdb,'r')
        f.close()
    except IOError:
        parser.error(\
              "Please check -d option: cannot read from subject FASTA filepath")
    if options.outputfilename is None:
        parser.error(\
                "Please check -f option: must specify base output path")  
    try:
        f=open(options.outputfilename,'w')
        f.close()
    except IOError:
        parser.error(\
              "Please check -f option: cannot write to output file")  


def format_options_as_lines(options):
    """Format options as a string for log file"""
    option_lines = []
    option_fields=str(options).split(",")
    
    for field in option_fields:
        option_lines.append(str(field).strip("{").strip("}"))
    
    return option_lines

def ids_to_seq_file(ids,infile,outfile,suffix=''):
    """Lookup FASTA recs for ids and record to file
    ids -- list of ids to lookup seqs for in infile

    infile -- path to FASTA file
    
    outfile -- base path to which to write FASTA entries
               with ids in supplied ids

    suffix  -- will be appended to outfile base path
    """

    seqs=seqs_from_file(ids, open(infile).readlines())
    out_path = outfile + suffix
    sequences_to_file(seqs,out_path) 

 
def main(options):

    DEBUG=options.debug
    start_time = time()  
    option_lines = format_options_as_lines(options)    
    if DEBUG:
        print FORMAT_BAR
        print "Running with options:"
        for line in sorted(option_lines):
            print line
        print FORMAT_BAR
    
   
    formatdb_cmd = 'formatdb -p F -o T -i %s' % options.subjectdb
    
    if DEBUG:
        print "Formatting subject db with command: %s" % formatdb_cmd
    
    system(formatdb_cmd)
    db_format_time = time() - start_time 
    
    if DEBUG:
        print "Formatting subject db took: %2.f seconds" % db_format_time
        print FORMAT_BAR 

    blast_results,hit_ids, removed_hit_ids=find_homologs(options.querydb,\
        options.subjectdb, options.e_value,options.max_hits,\
        options.working_dir,options.blastmatroot, options.wordsize,\
                            options.percent_aligned, DEBUG=DEBUG)
    
    blast_time = (time() - start_time) - db_format_time
    
    if DEBUG:
        print "BLAST search took: %2.f minute(s)" % (blast_time/60.0)
        print FORMAT_BAR
    
    #Record raw blast results
    f=open("%s.raw_blast_results" % options.outputfilename,'w')
    f.writelines(blast_results)
    f.close()

    #Record excluded seqs
    ids_to_seq_file(hit_ids,options.querydb,options.outputfilename,".excluded")

    #Record included (screened) seqs
    all_ids = ids_from_fasta_lines(open(options.querydb).readlines()) 
    included_ids  = set(all_ids) - hit_ids
    ids_to_seq_file(included_ids,options.querydb,options.outputfilename,".screened")
   
    log_lines = compose_logfile_lines(start_time, db_format_time, blast_time,\
                                                   option_lines,formatdb_cmd,\
                                               blast_results,options,all_ids,\
                                                     hit_ids,removed_hit_ids,\
                                                          included_ids,DEBUG)

    if DEBUG:
        print "Writing summary to: %s" % options.outputfilename +\
                                          ".sequence_exclusion_log"
      
    f=open(options.outputfilename + ".sequence_exclusion_log",'w')
    f.writelines(log_lines)
    f.close()
    

if __name__ == '__main__':
    option_parser=make_option_parser()
    (options,args)=option_parser.parse_args()
    check_options(option_parser, options) 
    main(options) 
   
