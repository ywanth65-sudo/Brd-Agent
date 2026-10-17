-- Collaboration, invitation, and chat persistence used by the FastAPI repository.
-- Apply this migration through the Supabase SQL editor or migration workflow.

create table if not exists project_collaborators (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects(id) on delete cascade,
    user_id uuid not null,
    user_email text not null,
    role text not null default 'editor' check (role in ('editor', 'viewer')),
    created_at timestamptz not null default now(),
    constraint uq_project_collaborator unique (project_id, user_id)
);

create index if not exists idx_project_collaborators_user
    on project_collaborators(user_id);
create index if not exists idx_project_collaborators_project
    on project_collaborators(project_id);

create table if not exists project_invitations (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects(id) on delete cascade,
    inviter_id uuid not null,
    inviter_email text not null,
    invitee_email text not null,
    role text not null default 'editor' check (role in ('editor', 'viewer')),
    status text not null default 'pending' check (status in ('pending', 'accepted', 'declined')),
    token uuid not null unique default gen_random_uuid(),
    created_at timestamptz not null default now(),
    accepted_at timestamptz
);

create index if not exists idx_project_invitations_invitee
    on project_invitations(lower(invitee_email), status);
create index if not exists idx_project_invitations_project
    on project_invitations(project_id, status);
create unique index if not exists uq_pending_project_invitation
    on project_invitations(project_id, lower(invitee_email))
    where status = 'pending';

create table if not exists project_chat_messages (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects(id) on delete cascade,
    sender_id uuid,
    sender_email text not null,
    sender_name text,
    role text not null check (role in ('user', 'assistant')),
    content text not null,
    created_at timestamptz not null default now()
);

create index if not exists idx_project_chat_messages_project
    on project_chat_messages(project_id, created_at);

alter table project_collaborators enable row level security;
alter table project_invitations enable row level security;
alter table project_chat_messages enable row level security;
