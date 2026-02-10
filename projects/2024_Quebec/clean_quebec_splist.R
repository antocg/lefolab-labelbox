library(tidyverse)
library(rgbif)

tree_sp_path <- "data/tree_sp_Quebec.txt"
shrub_sp_path <- "data/shrub_sp_Quebec.txt"

tree_species <- read.csv(tree_sp_path, sep = "\t", blank.lines.skip = TRUE)
shrub_species <- read.csv(shrub_sp_path, sep = "\t", blank.lines.skip = TRUE)

quebec_species <- bind_rows(tree_species, shrub_species) %>% 
  unique()

quebec_species_togbif <- quebec_species %>% 
  select(Scientific.name) %>% 
  mutate(Scientific.name = case_when(
    Scientific.name == "Amelanchier spicata" ~ "Amelanchier spicata (Lamarck) K. Koch",
    TRUE ~ Scientific.name))

quebec_species_gbif <- name_backbone_checklist(quebec_species_togbif, phylum = 'Tracheophyta')
not_exact <- quebec_species_gbif %>% filter(matchType != "EXACT")

quebec_species_gbif <- quebec_species_gbif %>% 
  mutate(gbif_accepted_scientific_name = ifelse(status %in% c("ACCEPTED", "DOUBTFUL"), canonicalName, species),
         gbif_accepted_taxon_id = ifelse(status %in% c("ACCEPTED", "DOUBTFUL"), usageKey, acceptedUsageKey),
         verbatim_name = case_when(
           verbatim_name == "Amelanchier spicata (Lamarck) K. Koch" ~ "Amelanchier spicata",
           TRUE ~ verbatim_name))

# Species ------
quebec_splist_withgbif <- quebec_species %>%
  left_join(quebec_species_gbif %>%
              select(verbatim_name, gbif_accepted_scientific_name, gbif_accepted_taxon_id),
            by = c("Scientific.name" = "verbatim_name"))

# Create taxon_column for Labelbox
quebec_splist_withgbif <- quebec_splist_withgbif %>%
  mutate(taxon_code = paste(Scientific.name, Vernacular.fr, sep = "-"))

write.csv(quebec_splist_withgbif, "data/labelbox_quebec_splist.csv",
          fileEncoding = 'latin1', row.names = F, quote = T)

# Families ------
familieslist <- quebec_species_gbif %>%
  select(family) %>% 
  distinct()

familieslist_gbif <- name_backbone_checklist(familieslist, phylum = 'Tracheophyta')
familieslist_withgbif <- familieslist_gbif %>% 
  select(taxon_code = verbatim_name,
         gbif_accepted_scientific_name = family,
         gbif_accepted_taxon_id = familyKey) %>% 
  arrange(gbif_accepted_scientific_name)

# Genera ------
generalist <- bind_rows(quebec_species_togbif %>%
                          mutate(genus = word(Scientific.name, 1)) %>%
                          select(genus),
                        quebec_species_gbif %>%
                          select(genus)) %>%
  distinct()

generalist_gbif <- name_backbone_checklist(generalist, phylum = 'Tracheophyta')
not_exact <- generalist_gbif %>% filter(matchType != "EXACT")

#Fix not exact matches
generalist_fixed <- generalist %>%
  mutate(name = paste(genus),
         name = case_when(
           name == "Aronia" ~ "Aronia Medik.",
           name == "Flueggea" ~ "Flueggea Willd.",
           TRUE ~ name
         )) %>%
  select(name)

generalist_gbif <- name_backbone_checklist(generalist_fixed, phylum = 'Tracheophyta')
not_exact <- generalist_gbif %>% filter(matchType != "EXACT")

# Join with original splist to add taxon codes, accepted scientific names and taxon IDs
generalist_withgbif <- generalist_gbif %>%
  mutate(gbif_accepted_scientific_name = ifelse(status %in% c("ACCEPTED", "DOUBTFUL"), canonicalName, genus),
         gbif_accepted_taxon_id = ifelse(status %in% c("ACCEPTED", "DOUBTFUL"), usageKey, acceptedUsageKey)) %>%
  select(verbatim_name, gbif_accepted_scientific_name, gbif_accepted_taxon_id) %>% 
  mutate(taxon_code = word(verbatim_name, 1)) %>% 
  select(-verbatim_name)

# Complete checklist for Labelbox ------
labelbox_quebec_checklist <- bind_rows(quebec_splist_withgbif,
                                    familieslist_withgbif,
                                    generalist_withgbif) %>% 
  select(taxon_code, gbif_accepted_taxon_id, gbif_accepted_scientific_name, Habit) %>% 
  mutate(across(everything(), 
                ~ifelse(is.na(.) | . == "NA", "", .))) %>% 
  arrange(taxon_code)

write.csv(labelbox_quebec_checklist, "data/labelbox_quebec_completelist.csv",
          fileEncoding = 'latin1', row.names = F, quote = T)
