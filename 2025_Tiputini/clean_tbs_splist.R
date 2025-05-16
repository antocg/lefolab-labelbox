library(tidyverse)
library(rgbif)

yasuni_species_path <- "data/YasuniTrapTaxonomyCodes_Garwood2023.csv"

yasuni_species <- read.csv(yasuni_species_path, blank.lines.skip = TRUE)


yasuni_species_cleaned <- yasuni_species %>% 
  filter(!apply(., 1, function(row) all(is.na(row) | row == "")),
         !grepl("Discontinued|Disconintued", UserNotes2018, ignore.case = TRUE),
         !grepl("Functional Codes", NombreMemoria, ignore.case = TRUE),
         !grepl("no identificado", NombreActual, ignore.case = TRUE),
         !grepl("Solanum semilla", NombreActual, ignore.case = TRUE),
         !(NombreActual == "Piper 'obchic'" & CodigoPBDY_18 == "")) %>% 
  mutate(NombreActual = case_when(
    grepl("^uniden", NombreActual) ~ paste0(Familia, " ", NombreActual),
    NombreActual == "Heisteria 'grande'" ~ "Heisteria Jacq. 'grande'",
    NombreActual == "Myroxylum balsamum" ~ "Myroxylon balsamum",
    NombreActual == "Dioclea reflexa" ~ "Dioclea reflexa (Hook.f.) C.Wright",
    NombreActual == "Odontodenia sp. A" ~ "Odontadenia sp. A",
    NombreActual == "Odontodenia sp. B" ~ "Odontadenia sp. B",
    NombreActual == "'Cladocolea' sp. Z" ~ "Cladocolea Tiegh.",
    NombreActual == "Pizona coriacea" ~ "Pinzona coriacea",
    TRUE ~ NombreActual
    )
  ) %>% 
  mutate(NombreMemoria = case_when(
    NombreMemoria == "(Poepp.) Kuntze" ~ "Dulacia candida",
    TRUE ~ NombreMemoria
    )
  )

# Add missing species
missing_species <- data.frame(
  Familia = c("Fabaceae", "Bignoniaceae", "Bignoniaceae", "Salicaceae",
              "Urticaceae", "Urticaceae", "Moraceae", "Fabaceae",
              "Cordiaceae", "Fabaceae"),
  NombreActual = c("Albizia niopoides", "Tabebuia ochracea", "Tabebuia serratifolia", "Banara nitida",
                   "Cecropia putumayonis", "Cecropia latiloba", "Ficus insipida", "Inga microcoma",
                   "Cordia alliodora", "Stryphnodendron porcatum"),
  stringsAsFactors = FALSE
) %>% 
  mutate(NombreMemoria = NombreActual)

# Append the manual species to the cleaned dataset
yasuni_species_cleaned <- bind_rows(yasuni_species_cleaned, missing_species)

yasuni_species_togbif <- yasuni_species_cleaned %>% 
  select(NombreActual)

yasuni_species_gbif <- name_backbone_checklist(yasuni_species_togbif, kingdom = 'Plantae')
not_exact <- yasuni_species_gbif %>% filter(matchType != "EXACT",
                                           rank != "SPECIES",
                                           !grepl("sp.", verbatim_name),
                                           !grepl("^[^']+\\s'[^']+'$", verbatim_name))

yasuni_species_gbif <- yasuni_species_gbif %>% 
  mutate(gbif_accepted_scientific_name = ifelse(status %in% c("ACCEPTED", "DOUBTFUL"), canonicalName, species),
         gbif_accepted_taxon_id = ifelse(status %in% c("ACCEPTED", "DOUBTFUL"), usageKey, acceptedUsageKey))

# Species ------
yasuni_splist_withgbif <- yasuni_species_cleaned %>%
  left_join(yasuni_species_gbif %>%
              select(verbatim_name, gbif_accepted_scientific_name, gbif_accepted_taxon_id),
            by = c("NombreActual" = "verbatim_name"))

# Create taxon_column for Labelbox
yasuni_splist_withgbif <- yasuni_splist_withgbif %>%
  mutate(taxon_code = case_when(
    ((CODIGO != "") & (CodigoPBDY_18 != "") & (CODIGO != CodigoPBDY_18)) ~ paste(toupper(CODIGO), toupper(CodigoPBDY_18), NombreMemoria, sep = '-'),
    ((CODIGO != "") & (CodigoPBDY_18 != "") & (CODIGO == CodigoPBDY_18)) ~ paste(toupper(CODIGO), NombreMemoria, sep = '-'),
    ((CODIGO != "") & (CodigoPBDY_18 == "")) ~ paste(toupper(CODIGO), NombreMemoria, sep = '-'),
    ((CODIGO == "") & (CodigoPBDY_18 != "")) ~ paste(toupper(CodigoPBDY_18), NombreMemoria, sep = '-'),
    .default = NombreMemoria))

write.csv(yasuni_splist_withgbif, "data/labelbox_tbs_splist.csv",
          fileEncoding = 'UTF-8', row.names = F, quote = T)

# Families ------
familieslist <- bind_rows(yasuni_species_cleaned %>%
                            select(Familia.APGIV, Familia) %>%
                            pivot_longer(cols = c(Familia.APGIV, Familia), names_to = "source", values_to = "family") %>%
                            select(family) %>% 
                            mutate(family = case_when(
                              family == "Bombacaeae" ~ "Bombacaceae",
                              family == "Verbenaceae?" ~ "Verbenaceae",
                              TRUE ~ family)),
                          yasuni_species_gbif %>%
                            select(family),
                          data.frame(family = c("Fabaceae-Mimosoideae", 
                                                "Fabaceae-Papilionoideae", 
                                                "Fabaceae-Caesalpiniodeae"))) %>%
  filter(!is.na(family),
         family != "") %>%
  distinct() %>% 
  mutate(name = family) %>% 
  mutate(name = case_when(
    str_detect(name, "Fabaceae") ~ "Fabaceae",
    TRUE ~ name
  ))


familieslist_gbif <- name_backbone_checklist(familieslist, kingdom = 'Plantae')
familieslist_withgbif <- familieslist_gbif %>% 
  select(taxon_code = verbatim_family,
         gbif_accepted_scientific_name = family,
         gbif_accepted_taxon_id = familyKey) %>% 
  arrange(gbif_accepted_scientific_name)

# Genera ------
generalist <- bind_rows(yasuni_species_cleaned %>%
                          mutate(genus = word(NombreActual, 1)) %>%
                          select(genus),
                        yasuni_species_cleaned %>%
                          mutate(genus = word(NombreMemoria, 1)) %>%
                          select(genus),
                        yasuni_species_gbif %>%
                          select(genus)) %>%
  distinct() %>% 
  filter(!is.na(genus),
         !genus %in% c("(no", "(unknown", "uniden.", "uniden", "Pizona", "Fosteronia"))

generalist_gbif <- name_backbone_checklist(generalist, phylum = 'Tracheophyta')
not_exact <- generalist_gbif %>% filter(matchType != "EXACT")

#Fix not exact matches
generalist_fixed <- generalist %>%
  mutate(name = paste(genus),
         name = case_when(
           name == "Heisteria" ~ "Heisteria Jacq.",
           name == "Hirtella" ~ "Hirtella L.",
           name == "Lunania" ~ "Lunania Hook.",
           name == "Simira" ~ "Simira Aubl.",
           TRUE ~ name
         )) %>%
  select(name)

generalist_gbif <- name_backbone_checklist(generalist_fixed, phylum = 'Tracheophyta')
not_exact <- generalist_gbif %>% filter(matchType != "EXACT")

# Join with original splist to add taxon codes, accepted scientific names and taxon IDs
generalist_withgbif <- generalist_gbif %>%
  filter(rank == "GENUS") %>% 
  mutate(gbif_accepted_scientific_name = ifelse(status %in% c("ACCEPTED", "DOUBTFUL"), canonicalName, genus),
         gbif_accepted_taxon_id = ifelse(status %in% c("ACCEPTED", "DOUBTFUL"), usageKey, acceptedUsageKey)) %>%
  select(verbatim_name, gbif_accepted_scientific_name, gbif_accepted_taxon_id) %>% 
  mutate(taxon_code = word(verbatim_name, 1)) %>% 
  select(-verbatim_name)

# Complete checklist for Labelbox ------
labelbox_tbs_checklist <- bind_rows(yasuni_splist_withgbif,
                                    familieslist_withgbif,
                                    generalist_withgbif) %>% 
  select(taxon_code, gbif_accepted_taxon_id, gbif_accepted_scientific_name, Forma_2015, FormaPBDY_2018) %>% 
  mutate(across(everything(), 
                ~ifelse(is.na(.) | . == "NA", "", .))) %>% 
  arrange(taxon_code)

write.csv(labelbox_tbs_checklist, "data/labelbox_tbs_completelist.csv",
          fileEncoding = 'latin1', row.names = F, quote = T)
