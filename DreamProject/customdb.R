library(BSgenome.Hsapiens.UCSC.hg19)
library(PGA)


createCustomDb <- function(snvOrindel, spliceJunctions, novelTrascripts, outputPath, fileName, sourceGenome){
  
  dbfile <- dbCreator(gtfFile=novelTrascripts,vcfFile=snvOrindel,bedFile=spliceJunctions,
                      annotation_path=outputPath,outfile_name=fileName,
                      genome=sourceGenome,outdir=outfile_path)
  
}