-- Schéma initial pour le stockage relationnel des données P&ID validées.
-- Les contraintes UNIQUE/PRIMARY KEY ci-dessous sont celles sur lesquelles
-- reposent les clauses ON CONFLICT de app/core/nodes.py::insert_postgres.

CREATE TABLE IF NOT EXISTS equipment (
    tag         TEXT PRIMARY KEY,          -- ex: 100-PU-01A, garanti unique dans tout le document
    name        TEXT NOT NULL,
    area        TEXT NOT NULL DEFAULT '',  -- dérivé du tag en code, jamais fourni par le LLM
    type        TEXT NOT NULL DEFAULT '',  -- dérivé du tag en code
    sequence    TEXT NOT NULL DEFAULT '',  -- dérivé du tag en code
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pipeline (
    id          BIGSERIAL PRIMARY KEY,
    from_tag    TEXT NOT NULL REFERENCES equipment(tag) ON DELETE CASCADE,
    to_tag      TEXT NOT NULL REFERENCES equipment(tag) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pipeline_from_to_unique UNIQUE (from_tag, to_tag),
    CONSTRAINT pipeline_no_self_loop CHECK (from_tag <> to_tag)
);

CREATE TABLE IF NOT EXISTS instrument (
    tag                 TEXT PRIMARY KEY,   -- unique dans tout le document, comme les équipements
    attached_to_tag     TEXT NOT NULL,      -- tag d'équipement OU id de pipeline selon attached_to_type
    attached_to_type    TEXT NOT NULL CHECK (attached_to_type IN ('equipment', 'pipeline')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- attached_to_tag ne peut pas être une clé étrangère unique vers deux tables
-- différentes (equipment.tag ou pipeline.id) en SQL standard : la cohérence
-- entre attached_to_type et l'existence réelle de la cible est donc vérifiée
-- côté application (dans insert_postgres), pas en contrainte SQL ici.

CREATE INDEX IF NOT EXISTS idx_pipeline_from_tag ON pipeline (from_tag);
CREATE INDEX IF NOT EXISTS idx_pipeline_to_tag ON pipeline (to_tag);
CREATE INDEX IF NOT EXISTS idx_instrument_attached_to_tag ON instrument (attached_to_tag);

-- Maintien automatique de updated_at sur UPDATE (déclenché par les
-- ON CONFLICT ... DO UPDATE de insert_postgres).
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_equipment_updated_at ON equipment;
CREATE TRIGGER trg_equipment_updated_at
    BEFORE UPDATE ON equipment
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_instrument_updated_at ON instrument;
CREATE TRIGGER trg_instrument_updated_at
    BEFORE UPDATE ON instrument
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();