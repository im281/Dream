## download packages
#source("https://bioconductor.org/biocLite.R")
#biocLite("PGA")


# download packages
#source("https://bioconductor.org/biocLite.R")
#biocLite("BSgenome.Hsapiens.UCSC.hg19")

#Load libraries
library(BSgenome.Hsapiens.UCSC.hg19)
library(PGA)

#Get RNA Seq data
vcffile <- system.file("extdata/input", "PGA.vcf",package="PGA")
bedfile <- system.file("extdata/input", "junctions.bed",package="PGA")
gtffile <- system.file("extdata/input", "transcripts.gtf",package="PGA")
annotation <- system.file("extdata", "annotation",package="PGA")
outfile_path<-"C:/tests"
outfile_name<-"test"

browseVignettes("PGA")

#Building database from RNA-Seq data

#Create custom database
dbfile <- dbCreator(gtfFile=gtffile,vcfFile=vcffile,bedFile=bedfile,
                    annotation_path=annotation,outfile_name=outfile_name,
                    genome=Hsapiens,outdir=outfile_path)



#Based on the result from de novo assembly of RNA-Seq data without
#a reference genome

transcript_seq_file <- system.file("extdata/input", "Trinity.fasta",
                                   package="PGA")
outdb <- createProDB4DenovoRNASeq(infa=transcript_seq_file,
                                  outfile_name = "C:/tests/denovo")


#MS/MS data searching
