drop table if exists public.containers cascade;

create table public.containers (
    "SHANA" integer,
    "RIV" integer,
    "HODESH" integer,
    "YEVUAN" integer,
    "KMUT" numeric(18,6),
    "SUG_ARIZA_MITZ" text,
    "SHEM_IZ" text,
    "SHEM_AR" text,
    "TARICH_PRIKA" date,
    "TARGET" integer,
    "SHIPNAME" text,
    "PEULA" text,
    "MANIFEST" integer
);

comment on table public.containers is 'Containers data imported from export.csv';
comment on column public.containers."SHANA" is 'Year';
comment on column public.containers."RIV" is 'Reference number / sequence';
comment on column public.containers."HODESH" is 'Month';
comment on column public.containers."YEVUAN" is 'Meaning: import/export flag (numeric code)';
comment on column public.containers."KMUT" is 'Quantity';
comment on column public.containers."SUG_ARIZA_MITZ" is 'Packaging type code';
comment on column public.containers."SHEM_IZ" is 'Line code (English letters)';
comment on column public.containers."SHEM_AR" is 'Line description (Hebrew)';
comment on column public.containers."TARICH_PRIKA" is 'Unload date (ISO date, parsed from export)';
comment on column public.containers."TARGET" is 'Target value';
comment on column public.containers."SHIPNAME" is 'Vessel name';
comment on column public.containers."PEULA" is 'Operation description';
comment on column public.containers."MANIFEST" is 'Manifest number';

grant select, insert, update, delete on table public.containers to service_role;

