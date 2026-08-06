create table caseifici (
    id bigint generated always as identity primary key,
    ragione_sociale text not null,
    sede_legale text,
    sede_operativa text,
    piva text,
    is_dop boolean not null default false,
    aut_852_numero text,
    aut_852_rilascio date,
    aut_852_scadenza date,
    aut_853_numero text,
    aut_853_rilascio date,
    aut_853_scadenza date,
    created_at timestamptz not null default now()
);

create table refrigeranti (
    id bigint generated always as identity primary key,
    caseificio_id bigint not null references caseifici(id) on delete cascade,
    codice text not null,
    nome text,
    capienza_kg numeric,
    attivo boolean not null default true
);

create table profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    ruolo text not null check (ruolo in ('owner','caseificio')),
    nome_visualizzato text,
    created_at timestamptz not null default now()
);

create table accessi_caseificio (
    id bigint generated always as identity primary key,
    profile_id uuid not null references profiles(id) on delete cascade,
    caseificio_id bigint not null references caseifici(id) on delete cascade,
    unique (profile_id, caseificio_id)
);

create table conferitori (
    id bigint generated always as identity primary key,
    caseificio_id bigint not null references caseifici(id) on delete cascade,
    tipo text not null check (tipo in ('allevatore','caseificio','intermediario','congelatore')),
    ragione_sociale text not null,
    sede_legale text,
    sede_operativa text,
    piva text,
    attivo boolean not null default true,
    ordine integer,
    created_at timestamptz not null default now()
);

create table conferitori_tipi_latte (
    id bigint generated always as identity primary key,
    conferitore_id bigint not null references conferitori(id) on delete cascade,
    tipo_latte text not null check (tipo_latte in (
        'bufala_dop','bufala','vaccino','cagliata_bufala',
        'cagliata_vaccino','bufala_congelato','vaccino_congelato','altro'
    ))
);

create table stati_sanitari (
    id bigint generated always as identity primary key,
    conferitore_id bigint not null references conferitori(id) on delete cascade,
    tipo text not null check (tipo in (
        'brucellosi','tubercolosi','leucosi','carica_batterica','cellule_somatiche'
    )),
    valore numeric,
    data_rilascio date,
    data_scadenza date,
    created_at timestamptz not null default now()
);

create table documenti_conferitori (
    id bigint generated always as identity primary key,
    conferitore_id bigint not null references conferitori(id) on delete cascade,
    tipo text not null check (tipo in ('autocertificazione','contratto')),
    data_scadenza date,
    file_url text,
    created_at timestamptz not null default now()
);

create table destinatari_vendita (
    id bigint generated always as identity primary key,
    caseificio_id bigint not null references caseifici(id) on delete cascade,
    tipo text not null check (tipo in ('caseificio','intermediario','congelatore_conto')),
    ragione_sociale text not null,
    sede_legale text,
    sede_operativa text,
    piva text,
    attivo boolean not null default true,
    created_at
