library(tidyverse)
library(readxl)
library(rgbif)

ducke_trees_path <- "data/arvores ducke.xlsx"
zf2_trees_path <- "data/arvores ZF2.xlsx"
ducke_lianas_path <- "data/lianas ducke.xlsx"

ducke_trees <- read_excel(ducke_trees_path)
zf2_trees <- read_excel(zf2_trees_path)
ducke_lianas <- read_excel(ducke_lianas_path)


manaus_species <- bind_rows(ducke_trees %>% 
                              mutate(habit = "Freestanding",
                                     site = "Ducke"),
                            zf2_trees %>% 
                              mutate(habit = "Freestanding",
                                     site = "ZF2"),
                            ducke_lianas %>% 
                              mutate(habit = "Climbing",
                                     site = "Ducke")) %>% 
  distinct()
  
manaus_species_togbif <- manaus_species %>% 
  select(CalcAcceptedName)

manaus_species_gbif <- name_backbone_checklist(manaus_species_togbif, kingdom = 'Plantae')
not_exact <- manaus_species_gbif %>% filter(matchType != "EXACT")

manaus_species_cleaned <- manaus_species %>% 
  mutate(CalcAcceptedName = case_when(
    CalcAcceptedName == "Elizabetha speciosa Ducke" ~ "Paloue speciosa (Ducke) Redden", # synonym
    CalcAcceptedName == "Sloanea obtusa (Splitg.) Schum." ~ "Sloanea kappleriana Pulle", # synonym
    TRUE ~ CalcAcceptedName))

manaus_species_togbif <- manaus_species_cleaned %>% 
  select(CalcAcceptedName)

manaus_species_gbif <- name_backbone_checklist(manaus_species_togbif, kingdom = 'Plantae')
not_exact <- manaus_species_gbif %>% filter(matchType != "EXACT")

manaus_species_gbif <- manaus_species_gbif %>% 
  mutate(gbif_accepted_scientific_name = ifelse(status %in% c("ACCEPTED", "DOUBTFUL"), canonicalName, species),
         gbif_accepted_taxon_id = ifelse(status %in% c("ACCEPTED", "DOUBTFUL"), usageKey, acceptedUsageKey)) %>% 
  distinct(verbatim_name, .keep_all = TRUE)

# Species ------
manaus_splist_withgbif <- manaus_species_cleaned %>%
  left_join(manaus_species_gbif %>%
              select(verbatim_name, gbif_accepted_scientific_name, gbif_accepted_taxon_id),
            by = c("CalcAcceptedName" = "verbatim_name")) %>% 
  mutate(CalcAcceptedName = case_when(
    CalcAcceptedName == "Paloue speciosa (Ducke) Redden" ~ "Elizabetha speciosa Ducke", # synonym
    CalcAcceptedName == "Sloanea kappleriana Pulle" ~ "Sloanea obtusa (Splitg.) Schum.", # synonym
    TRUE ~ CalcAcceptedName))

# Create taxon_column for Labelbox
manaus_splist_withgbif <- manaus_splist_withgbif %>%
  mutate(taxon_code = CalcAcceptedName)

write.csv(manaus_splist_withgbif, "data/labelbox_manaus_splist.csv",
          fileEncoding = 'UTF-8', row.names = F, quote = T)

# Families ------
familieslist <- bind_rows(manaus_species_cleaned %>%
                            rename(family = FamilyName) %>% 
                            select(family),
                          manaus_species_gbif %>%
                            select(family),
                          data.frame(family = c("Fabaceae-Mimosoideae", 
                                                "Fabaceae-Papilionoideae", 
                                                "Fabaceae-Caesalpiniodeae"))) %>%
  distinct() %>% 
  mutate(name = family) %>% 
  mutate(name = case_when(
    str_detect(name, "Fabaceae|Leguminosae") ~ "Fabaceae",
    TRUE ~ name
  ))


familieslist_gbif <- name_backbone_checklist(familieslist, kingdom = 'Plantae')
familieslist_withgbif <- familieslist_gbif %>% 
  select(taxon_code = verbatim_family,
         gbif_accepted_scientific_name = family,
         gbif_accepted_taxon_id = familyKey) %>% 
  arrange(gbif_accepted_scientific_name)

# Genera ------
generalist <- bind_rows(manaus_species_cleaned %>%
                          mutate(genus = word(CalcAcceptedName, 1)) %>%
                          select(genus),
                        manaus_species_gbif %>%
                          select(genus)) %>%
  distinct()

generalist_gbif <- name_backbone_checklist(generalist, phylum = 'Tracheophyta')
not_exact <- generalist_gbif %>% filter(matchType != "EXACT")

#Fix not exact matches
generalist_fixed <- generalist %>%
  mutate(name = paste(genus),
         name = case_when(
           name == "Heisteria" ~ "Heisteria Jacq.",
           name == "Hirtella" ~ "Hirtella L.",
           name == "Scleronema" ~ "Scleronema Benth.",
           name == "Cuspidaria" ~ "Cuspidaria DC.",
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
labelbox_manaus_checklist <- bind_rows(manaus_splist_withgbif,
                                    familieslist_withgbif,
                                    generalist_withgbif) %>% 
  select(taxon_code, gbif_accepted_taxon_id, gbif_accepted_scientific_name, habit) %>% 
  mutate(across(everything(), 
                ~ifelse(is.na(.) | . == "NA", "", .))) %>% 
  distinct(taxon_code, .keep_all = TRUE) %>% 
  arrange(taxon_code)

write.csv(labelbox_manaus_checklist, "data/labelbox_manaus_completelist.csv",
          fileEncoding = 'UTF-8', row.names = F, quote = T)
