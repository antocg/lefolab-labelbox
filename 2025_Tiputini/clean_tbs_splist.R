library(tidyverse)
library(rgbif)

yasuni_splist_path <- "Labelbox/2025_Tiputini/data/YasuniTrapTaxonomyCodes_Garwood2023.csv"

yasuni_splist <- read.csv(yasuni_splist_path, blank.lines.skip = TRUE)


yasuni_splist_cleaned <- yasuni_splist %>% 
  filter(!apply(., 1, function(row) all(is.na(row) | row == ""))) %>% 
  filter(!grepl("Discontinued|Disconintued", UserNotes2018, ignore.case = TRUE)) %>% 
  filter(!grepl("Functional Codes", NombreMemoria, ignore.case = TRUE)) %>% 
  filter(!grepl("no identificado", NombreActual, ignore.case = TRUE))
