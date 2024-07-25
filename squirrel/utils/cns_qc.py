#!/usr/bin/env python3
import sys
import os
from squirrel.utils.log_colours import green,cyan
import select
from Bio import SeqIO
import collections
import csv
from squirrel.utils.config import *

import baltic as bt
import matplotlib as mpl
import matplotlib.pyplot as plt
import seaborn as sns
import collections
import pandas as pd

plt.switch_backend('Agg') 


mpl.rcParams.update({'font.size': 18})

new_rc_params = {'text.usetex': False,
"svg.fonttype": 'none'
}
mpl.rcParams.update(new_rc_params)
plt.rcParams['font.family'] = 'Helvetica'


def add_refs_to_input(input_fasta,assembly_refs,config):
    new_input_fasta = os.path.join(config[KEY_TEMPDIR], "qcref_combined.fasta")
    with open(new_input_fasta,"w") as fw:
        for record in SeqIO.parse(input_fasta,"fasta"):
            fw.write(f">{record.id}\n{record.seq}\n")
        for record in assembly_refs:
            fw.write(f">{record.id}\n{record.seq}\n")
    return new_input_fasta


def find_assembly_refs(cwd,assembly_refs,config):

    if not assembly_refs:
        sys.stderr.write(cyan(f'Error: no assembly references supplied.\nMust supply a reference file with one or more assembly references to do sequence QC.\n'))
        sys.exit(-1)

    refs = []
    ref_ids = []
    path_to_try = os.path.join(cwd,assembly_refs)
    try:
        for record in SeqIO.parse(path_to_try,"fasta"):
            refs.append(record)
            ref_ids.append(record.id)
    except:
        sys.stderr.write(cyan(f'Error: cannot find/parse reference fasta file at: ') + f'{path_to_try}\n' + cyan('Please check file path and format.\n'))
        sys.exit(-1)

    config[KEY_ASSEMBLY_REFERENCES] = ref_ids

    return refs

def recurse_back(node):
    path = [node.traits["label"]]
    p = node.parent
    while p.traits["label"] != "Node1":
        path.append(p.traits["label"])
        p = p.parent
    path.append("Node1")
    return path

def get_path_to_root(treefile):
    
    """
    traces back from a given tip through each parent 
    and returns a list of branches that make up the 
    phylo path from root to tip

    """
    my_tree=bt.loadNewick(treefile,absoluteTime=False)

    for k in my_tree.Objects:
        current_node = k
        if k.branchType == 'leaf':
            current_node.traits["label"]=k.name
            
            node_name = current_node.traits["label"]
            try:
                parent_name = current_node.parent.traits["label"]
            except:
                continue
    
    branch_paths = {}
    
    for k in my_tree.Objects:
        current_node = k
        
        if current_node.branchType == 'leaf':
            path = recurse_back(current_node)
            branch_path = []
            for i in range(len(path)-1, 0, -1):
                try:
                    branch = f"{path[i]}_{path[i-1]}"
                    branch_path.append(branch)
                except:
                    print("breaks",path)
#             print(current_node.traits["label"])
#             print(branch_path)
            branch_paths[current_node.traits["label"]] = branch_path
    return branch_paths


def read_in_branch_snps(branch_snps):
    branch_snps_dict = collections.defaultdict(list)
    with open(branch_snps,"r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            branch = f"{row['parent']}_{row['child']}"
            branch_snps_dict[branch].append((row['site'],row['snp'],row['dimer'])) 
    return branch_snps_dict

def get_seq_at_node(state_file,nodename):
    
    """
    returns a dict keys off 1-based positions in the genome
    and the value is a list of tuples (id, base) at a given node
    allows you to look up for a given site what the base is for a
    given internal node or tip
    """
    seq = ""
    with open(f"{state_file}","r") as f:
        for l in f:

            if not l.startswith("#"):
                try:
                    node,site,state,probA,probC,probG,probT = l.rstrip("\n").split("\t")
                except:
                    print(l)
                    break
                if node == nodename:
                    seq+=state

    return seq

def load_assembly_refs(assembly_refs):

    refs = {}
    for record in assembly_refs:
        refs[record.id] = record.seq
    return refs


def flag_reversions(branch_paths, branch_snp_dict, refs, root_node):
    possible_reversions = []
    branch_reversions = collections.defaultdict(set)
    snp_to_branch = {}
    will_be_reverted = collections.defaultdict(set)
    for tip in branch_paths:
        path_snps = []
        for branch in branch_paths[tip]:
            snps = branch_snp_dict[branch]
            for i in snps:
                
                if i[0] in [j[0] for j in path_snps]:
                    base = int(i[0])
                    
                    allele = i[1][-1]
                    
                    branch_reversions[branch].add(f"{base}{allele}")
                    will_be_reverted[snp_to_branch[i[0]]].add(f"{base}{i[1][0]}")
                    reversion_to = []
                    
                    ref_alleles = []
                    for ref in refs:
                        var = refs[ref][base-1]
                        ref_alleles.append(f"{ref}:{var}")
                        if allele == var:
                            reversion_to.append(ref)
                        
                    root_var = root_node[base-1]
                    if allele == root_var:
                        reversion_to.append("Root")
                    
                    original_snp = [k for k in path_snps if k[0] == i[0]][0]
                    
                    possible_reversions.append({
                        "taxon":tip,
                        "site":i[0],
                        "original_snp": original_snp[1],
                        "original_branch":snp_to_branch[i[0]],
                        "reversion_branch":branch,
                        "dinucleotide_context": original_snp[2],
                        "reversion_snp": i[1],
                        "reference_alleles": ";".join(ref_alleles),
                        "root_allele":root_node[base-1],
                        "reversion_to":";".join(reversion_to)
                    })

                
                snp_to_branch[i[0]] = branch
                path_snps.append(i)
    if branch_reversions:
        print(green("Reversions flagged:"))
        for i in branch_reversions:
            print(f"- {i} {branch_reversions[i]}")
    return possible_reversions,branch_reversions,will_be_reverted


def flag_convergence(treefile, branch_snp_dict):
    snp_to_branch = collections.defaultdict(set)
    branch_convergence = collections.defaultdict(set)

    my_tree=bt.loadNewick(treefile,absoluteTime=False)

    for k in my_tree.Objects:
        current_node = k
        if k.branchType == 'leaf':
            current_node.traits["label"]=k.name
            node_name = current_node.traits["label"]
            
        try:
            parent_name = current_node.parent.traits["label"]
            node_name = current_node.traits["label"]
        except:
            continue
        
        branch = f"{parent_name}_{node_name}"

        snps = branch_snp_dict[branch]
        for i in snps:
            snp_to_branch[i].add(branch)
    convergent_snps= []
    for snp in snp_to_branch:
        if len(snp_to_branch[snp])> 1:
            report_snp = f"{snp[1][0]}{snp[0]}{snp[1][-1]}"
            convergent_snps.append(report_snp)
            for branch in snp_to_branch[snp]:
                branch_convergence[branch].add(report_snp)

    if convergent_snps:
        print("Convergent snps flagged:")
        for i in convergent_snps:
            print(f"- {i}")
    return branch_convergence


def make_reversion_tree_figure(outfile,branch_snps,branch_reversions,will_be_reverted,treefile,w,h):
    
    branch_snps_dict = read_in_branch_snps(branch_snps)

    my_tree=bt.loadNewick(treefile,absoluteTime=False)

    fig,ax = plt.subplots(figsize=(w,h),facecolor='w')

    x_attr=lambda k: k.height ## x coordinate of branches will be absoluteTime attribute
    su_func=lambda k: 50-30*k.height/my_tree.treeHeight ## size of tips
    s_func=lambda k: 50-20*k.height/my_tree.treeHeight ## size of tips
    c_func=lambda k: "dimgrey"

    increment = my_tree.treeHeight/150
    my_tree.plotTree(ax,x_attr=x_attr) ## plot branches
    my_tree.plotPoints(ax,size=s_func,colour=c_func,x_attr=x_attr) ## plot circles at tips
    mpl.rcParams['font.family'] = 'sans-serif'

    target_func=lambda k: k.is_leaf() ## which branches will be annotated
    text_func=lambda k: k.name ## what text is plotted
    text_x_attr=lambda k: k.height+(increment*4) ## where x coordinate for text is

    my_tree.addText(ax,x_attr=text_x_attr,target=target_func,text=text_func) #
    
    for k in my_tree.Objects:
        current_node = k
        if k.branchType == 'leaf':
            current_node.traits["label"]=k.name

        node_name = current_node.traits["label"]
        try:
            parent_name = current_node.parent.traits["label"]
        except:
            continue
        branch_name= f"{parent_name}_{node_name}"
        
        if branch_name in branch_snps_dict:
            snps = []
            reversions = []
            tb_reversions = []
            if branch_name in branch_reversions:
                for s in branch_reversions[branch_name]:
                    reversions.append(s)
#                 print(branch_name, len(branch_snps_dict[branch_name]))
            if branch_name in will_be_reverted:
                for s in will_be_reverted[branch_name]:
                    tb_reversions.append(s)
            snp_placement = current_node.parent.height + increment
            rev_placement = (current_node.parent.height + current_node.height)/2
            tb_rev_placement = (current_node.parent.height + current_node.height)/2
            for s in branch_snps_dict[branch_name]:
                site,snp,dimer = s
                if snp == "G->A":
                    if dimer in ["GA"]:
                        snps.append((1,"#995e62"))
                    else:
                        snps.append((2,"#d9b660"))
                elif snp == "C->T":
                    if dimer in ["TC"]:
                        snps.append((1,"#995e62"))
                    else:
                        snps.append((2,"#d9b660"))
                else:
                    snps.append((2,"#d9b660"))
            
            for reversion in reversions:
                plt.text(s=reversion,x=rev_placement,y=k.y+0.5,rotation="vertical")
                plt.scatter([rev_placement],[k.y],color="black",s=150,marker=8)
                rev_placement += 3*increment
            for tb_reversion in tb_reversions:
                plt.text(s=tb_reversion,x=tb_rev_placement,y=k.y+0.5,rotation="vertical")
                plt.scatter([tb_rev_placement],[k.y],color="black",s=150,marker=9)
                tb_rev_placement += 3*increment

            for snp in sorted(snps, key = lambda x : x[0]):
                plt.scatter([snp_placement],[k.y+0.5],color=snp[1],s=30)
                snp_placement += increment

    [ax.spines[loc].set_visible(False) for loc in ['top','right','left','bottom']]
    ax.tick_params(axis='y',size=0)
    ax.tick_params(axis='x',size=0)

    ax.set_yticklabels([])
    ax.set_xticklabels([])

    plt.savefig(f"{outfile}.svg",bbox_inches='tight')
    plt.savefig(f"{outfile}.png",bbox_inches='tight', 
                   transparent=True)
    # plt.show()

def make_convergence_tree_figure(outfile,branch_snps,branch_convergence,treefile,w,h):
    
    branch_snps_dict = read_in_branch_snps(branch_snps)

    my_tree=bt.loadNewick(treefile,absoluteTime=False)

    fig,ax = plt.subplots(figsize=(w,h),facecolor='w')

    x_attr=lambda k: k.height ## x coordinate of branches will be absoluteTime attribute
    su_func=lambda k: 50-30*k.height/my_tree.treeHeight ## size of tips
    s_func=lambda k: 50-20*k.height/my_tree.treeHeight ## size of tips
    c_func=lambda k: "dimgrey"

    increment = my_tree.treeHeight/150
    my_tree.plotTree(ax,x_attr=x_attr) ## plot branches
    my_tree.plotPoints(ax,size=s_func,colour=c_func,x_attr=x_attr) ## plot circles at tips
    mpl.rcParams['font.family'] = 'sans-serif'

    target_func=lambda k: k.is_leaf() ## which branches will be annotated
    text_func=lambda k: k.name ## what text is plotted
    text_x_attr=lambda k: k.height+(increment*4) ## where x coordinate for text is

    my_tree.addText(ax,x_attr=text_x_attr,target=target_func,text=text_func) #
    
    for k in my_tree.Objects:
        current_node = k
        if k.branchType == 'leaf':
            current_node.traits["label"]=k.name

        node_name = current_node.traits["label"]
        try:
            parent_name = current_node.parent.traits["label"]
        except:
            continue
        branch_name= f"{parent_name}_{node_name}"
        
        if branch_name in branch_snps_dict:
            snps = []
            convergent_snps = []
            if branch_name in branch_convergence:
                for s in branch_convergence[branch_name]:
                    convergent_snps.append(s)
#                 print(branch_name, len(branch_snps_dict[branch_name]))

            snp_placement = current_node.parent.height + increment
            c_placement = (current_node.parent.height + current_node.height)/2
            for s in branch_snps_dict[branch_name]:
                site,snp,dimer = s
                if snp == "G->A":
                    if dimer in ["GA"]:
                        snps.append((1,"#995e62"))
                    else:
                        snps.append((2,"#d9b660"))
                elif snp == "C->T":
                    if dimer in ["TC"]:
                        snps.append((1,"#995e62"))
                    else:
                        snps.append((2,"#d9b660"))
                else:
                    snps.append((2,"#d9b660"))
            
            for c_snp in convergent_snps:
                plt.text(s=c_snp,x=c_placement,y=k.y+0.5,rotation="vertical")
                plt.scatter([c_placement],[k.y],color="black",s=150,marker="d")
                c_placement += 2*increment

            for snp in sorted(snps, key = lambda x : x[0]):
                plt.scatter([snp_placement],[k.y+0.5],color=snp[1],s=30)
                snp_placement += increment

    [ax.spines[loc].set_visible(False) for loc in ['top','right','left','bottom']]
    ax.tick_params(axis='y',size=0)
    ax.tick_params(axis='x',size=0)

    ax.set_yticklabels([])
    ax.set_xticklabels([])

    plt.savefig(f"{outfile}.svg",bbox_inches='tight')
    plt.savefig(f"{outfile}.png",bbox_inches='tight', 
                   transparent=True)


def check_for_snp_anomalies(config,h):

    state_file = os.path.join(config[KEY_OUTDIR],f"{config[KEY_OUTFILENAME]}.state")
    treefile = os.path.join(config[KEY_OUTDIR],f"{config[KEY_OUTFILENAME]}.treefile")
    branch_snps = os.path.join(config[KEY_OUTDIR],f"{config[KEY_PHYLOGENY]}.branch_snps.reconstruction.csv")
    reversion_out = os.path.join(config[KEY_OUTDIR],f"{config[KEY_OUTFILENAME]}.reversions.csv")
    convergence_out = os.path.join(config[KEY_OUTDIR],f"{config[KEY_OUTFILENAME]}.convergence.csv")
    reversion_figure_out = os.path.join(config[KEY_OUTDIR],f"{config[KEY_OUTFILENAME]}.reversions_fig")
    convergence_figure_out = os.path.join(config[KEY_OUTDIR],f"{config[KEY_OUTFILENAME]}.convergence_fig")
    mask_file = os.path.join(config[KEY_OUTDIR],f"{config[KEY_OUTFILENAME]}.suggested_mask.csv")

    branch_snp_dict = read_in_branch_snps(branch_snps)
    branch_paths= get_path_to_root(treefile)

    refs = load_assembly_refs(assembly_refs)
    node1 = get_seq_at_node(state_file,"Node1")

    possible_reversions,branch_reversions,will_be_reverted = flag_reversions(branch_paths, branch_snp_dict, refs, node1)  
    branch_convergence = flag_convergence(treefile, branch_snp_dict)

    with open(convergence_out, "w") as fw:
        fw.write("branch,snp\n")
        for branch in branch_convergence:
            for snp in branch_convergence[branch]:
                fw.write(f"{branch},{snp}\n")

    with open(reversion_out, "w") as fw:
        writer= csv.DictWriter(fw,lineterminator="\n",fieldnames = ["taxon","site","original_snp","original_branch",
                                                                    "dinucleotide_context",
                                                                    "reversion_snp","reference_alleles",
                                                                    "root_allele","reversion_to","reversion_branch"
                                                                   ])
        writer.writeheader()
        for i in possible_reversions:
            writer.writerow(i)
            
    make_reversion_tree_figure(reversion_figure_out,branch_snps,branch_reversions,will_be_reverted,treefile,25,h)
    make_convergence_tree_figure(convergence_figure_out,branch_snps,branch_convergence,treefile,25,h)

    with open(mask_file,"w") as fw:
        fw.write("Name,Minimum,Maximum,Length\n")
        for i in branch_reversions:
            for j in branch_reversions[i]:
                site = int(j[:-1])
                allele = j[-1]
                fw.write(f"{i} reversion to {allele},{site},{site},{1}\n")


