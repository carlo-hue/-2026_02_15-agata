-- DDL minimo locale per persistenza TPF in AGATA
-- Nota: per i cataloghi TPF, agata_star_photometry.hjd contiene valori BJD_TDB.

CREATE TABLE IF NOT EXISTS agata_star_photometry (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    hjd DOUBLE NOT NULL,
    Vmag DOUBLE NOT NULL,
    Source BIGINT UNSIGNED NOT NULL,
    catalogo VARCHAR(100) NOT NULL,
    catalog_import_id BIGINT UNSIGNED NULL,
    association_id_owner BIGINT UNSIGNED NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY ix_agata_star_photometry_source (Source),
    KEY ix_agata_star_photometry_catalogo (catalogo),
    KEY ix_agata_star_photometry_hjd (hjd),
    KEY ix_agata_star_photometry_source_hjd (Source, hjd)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agata_star (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    gaia_id BIGINT UNSIGNED NOT NULL,
    total_points INT UNSIGNED NOT NULL DEFAULT 0,
    num_catalogs INT UNSIGNED NOT NULL DEFAULT 0,
    catalogs JSON NULL,
    min_hjd DOUBLE NULL,
    max_hjd DOUBLE NULL,
    min_mag DOUBLE NULL,
    max_mag DOUBLE NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_agata_star_gaia_id (gaia_id),
    KEY ix_agata_star_gaia_id (gaia_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agata_tpf_sessions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    gaia_source_id BIGINT UNSIGNED NOT NULL,
    sector INT UNSIGNED NOT NULL,
    catalog_name VARCHAR(100) NOT NULL,
    mode VARCHAR(64) NOT NULL,
    mask_origin VARCHAR(32) NOT NULL,
    tpf_filename VARCHAR(255) NULL,
    tpf_path TEXT NULL,
    target_mask_json JSON NOT NULL,
    background_mask_json JSON NOT NULL,
    lightcurve_json JSON NOT NULL,
    metadata_json JSON NULL,
    saved_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    saved_by VARCHAR(100) NULL,
    is_promoted BOOLEAN NOT NULL DEFAULT FALSE,
    promoted_points INT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    KEY ix_agata_tpf_sessions_gaia_sector (gaia_source_id, sector),
    KEY ix_agata_tpf_sessions_saved_at (saved_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
