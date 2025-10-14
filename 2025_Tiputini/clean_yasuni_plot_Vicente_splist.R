library(tidyverse)
library(rgbif)

yasuni_species_path <- "data/yasuni_plot_Vicente.csv"

yasuni_species <- read.csv(yasuni_species_path, blank.lines.skip = TRUE, fileEncoding = 'latin1') 

yasuni_species_cleaned = yasuni_species %>%
  mutate(Species = paste(Genus, SpeciesName, sep = " ")) %>%
  mutate(Species = case_when(
    Species == "Piper macrophyllum" ~ "Piper macrophyllum Sw.",
    Species == "Psychotria caerulea" ~ "Psychotria caerulea Ruiz & Pav.",
    TRUE ~ Species))

yasuni_species_only_cleaned = yasuni_species_cleaned %>%
  filter(Idlevel == 'species')

yasuni_species_togbif <- yasuni_species_only_cleaned %>% 
  select(Species)

yasuni_species_gbif <- name_backbone_checklist(yasuni_species_togbif, kingdom = 'Plantae')
not_exact <- yasuni_species_gbif %>% filter(matchType != "EXACT")

yasuni_species_gbif <- yasuni_species_gbif %>% 
  mutate(gbif_accepted_scientific_name = ifelse(status %in% c("ACCEPTED", "DOUBTFUL"), canonicalName, species),
         gbif_accepted_taxon_id = ifelse(status %in% c("ACCEPTED", "DOUBTFUL"), usageKey, acceptedUsageKey))

# Species ------
yasuni_splist_withgbif <- yasuni_species_only_cleaned %>%
  left_join(yasuni_species_gbif %>%
              select(verbatim_name, gbif_accepted_scientific_name, gbif_accepted_taxon_id),
            by = c("Species" = "verbatim_name"))

# Create taxon_column for Labelbox
yasuni_splist_withgbif <- yasuni_splist_withgbif %>%
  mutate(taxon_code = paste(Mnemonic, paste(Genus, SpeciesName, sep = " "), sep = "-"))

write.csv(yasuni_splist_withgbif, "data/yasuni_plot_splist.csv",
          fileEncoding = 'latin1', row.names = F, quote = T)

# Families ------
yasuni_families_cleaned = yasuni_species_cleaned %>%
  filter(Idlevel == 'family') %>%
  rename(family = Family) %>%
  rename(name = Species)

familieslist_gbif <- name_backbone_checklist(yasuni_families_cleaned, kingdom = 'Plantae')

familieslist_withgbif <- yasuni_families_cleaned %>% 
  left_join(familieslist_gbif %>%
              mutate(gbif_accepted_scientific_name = family,
                     gbif_accepted_taxon_id = familyKey) %>%
              select(verbatim_name, gbif_accepted_scientific_name, gbif_accepted_taxon_id),
            by = c("name" = "verbatim_name")) %>%
  arrange(gbif_accepted_scientific_name)

familieslist_withgbif <- familieslist_withgbif %>%
  mutate(taxon_code = paste(Mnemonic, paste(Genus, SpeciesName, sep = " "), sep = "-"))

# Genera ------
yasuni_genera_cleaned = yasuni_species_cleaned %>%
  filter(Idlevel == 'genus') %>%
  rename(family = Family) %>%
  rename(name = Species)

generalist_gbif <- name_backbone_checklist(yasuni_genera_cleaned, phylum = 'Tracheophyta')
not_exact <- generalist_gbif %>% filter(matchType != "EXACT")

generalist_withgbif <- yasuni_genera_cleaned %>% 
  left_join(generalist_gbif %>%
              mutate(gbif_accepted_scientific_name = genus,
                     gbif_accepted_taxon_id = genusKey) %>%
              select(verbatim_name, gbif_accepted_scientific_name, gbif_accepted_taxon_id),
            by = c("name" = "verbatim_name")) %>%
  arrange(gbif_accepted_scientific_name)

generalist_withgbif <- generalist_withgbif %>%
  mutate(taxon_code = paste(Mnemonic, paste(Genus, SpeciesName, sep = " "), sep = "-"))

# Complete checklist for Labelbox ------
labelbox_yasuni_checklist <- bind_rows(yasuni_splist_withgbif,
                                    familieslist_withgbif,
                                    generalist_withgbif) %>% 
  select(taxon_code, gbif_accepted_taxon_id, gbif_accepted_scientific_name, Idlevel) %>% 
  arrange(taxon_code)

write.csv(labelbox_yasuni_checklist, "data/labelbox_yasuni_plot_completelist.csv",
          fileEncoding = 'latin1', row.names = F, quote = T)
