# squirrel

**S**ome **QUI**ck **R**earranging to **R**esolve **E**volutionary **L**inks

## Generate a quick monkeypox alignment

```
usage: squirrel <input> [options]

squirrel: Some QUIck Rearranging to Resolve Evolutionary Links

optional arguments:
  -h, --help            show this help message and exit

Input-Output options:
  input                 Input fasta file of sequences to analyse.
  -o OUTDIR, --outdir OUTDIR
                        Output directory. Default: current working directory
  --outfile OUTFILE     Optional output file name. Default: <input>.aln.fasta
  --tempdir TEMPDIR     Specify where you want the temp stuff to go. Default: $TMPDIR
  --no-temp             Output all intermediate files, for dev purposes.

Pipeline options:
  --no-mask             Skip masking of repetitive regions. Default: masks repeat regions
  --no-itr-mask         Skip masking of end ITR. Default: masks ITR
  --extract-cds         Extract coding sequences based on coordinates in the reference
  --concatenate         Concatenate coding sequences for each genome, separated by `NNN`. Default: write out as separate records
  -p, --run-phylo       Run phylogenetic reconstruction pipeline
  --outgroups OUTGROUPS
                        Specify which MPXV outgroup(s) in the alignment to use in the phylogeny. These will get pruned out from the final tree.

Misc options:
  -v, --version         show program's version number and exit
  --verbose             Print lots of stuff to screen
  -t THREADS, --threads THREADS
                        Number of threads
```

## How it works

Squirrel maps each query genome in the input file against the NC_063383 reference genome using [minimap2](https://academic.oup.com/bioinformatics/article/34/18/3094/4994778). It then trims to 190788 at the end of the genome to mask out one of the ITR regions and pads the end of the genome with `N`. It performs masking (replacement with `N`) on low-complexity or repetitive regions, defined [here](https://github.com/aineniamh/squirrel/blob/main/squirrel/data/to_mask.csv). The masking can be toggled on and off.
Using [gofasta](https://academic.oup.com/bioinformatics/article/38/16/4033/6631223), the map file is then converted into a multiple sequence alignment. 

Squirrel by default creates a single alignment fasta file. Using the genbank coordinates for NC_063383 it also has the ability to extract the aligned coding sequences either as separate records or as a concatenated alignment. This can facilitate codon-aware phylogenetic or sequence analysis.

## Installation

1. Clone this repository and ``cd squirrel``
2. ``conda env create -f environment.yml``
3. ``conda activate squirrel``
4. ``pip install .``

## Check the install worked

Type (in the <strong>squirrel</strong> environment):

```
squirrel -v
```
and you should see the versions of <strong>squirrel</strong>.
