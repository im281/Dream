source("http://depot.sagebase.org/CRAN.R")
pkgInstall(c("synapseClient"))


library(synapseClient)
# If you have your config file set up you can run:
synapseLogin()
# Otherwise, pass in your username and password:
synapseLogin(username='im281@synapse.com', password='secret', rememberMe=TRUE)

myProj <- synStore(Project(name="Project Proteogenomics test"))
print(paste('Created a project with Synapse id', myProj$properties$id, sep = ' '))

onWeb(myProj)

#Folder/Project synID: syn123
q <- synQuery('SELECT id, name FROM entity WHERE parentId=="syn123"')
print(q)
