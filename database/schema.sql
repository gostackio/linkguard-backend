-- Enable required extensions
create extension if not exists "uuid-ossp";
create extension if not exists "pg_crypto";

-- Users table
create table users (
    id uuid primary key default uuid_generate_v4(),
    email varchar(255) unique not null,
    password_hash varchar(255) not null,
    name varchar(255) not null,
    website varchar(255),
    created_at timestamp with time zone default now(),
    updated_at timestamp with time zone default now()
);

-- Links table
create table links (
    id uuid primary key default uuid_generate_v4(),
    url text not null,
    title varchar(255) not null,
    page varchar(255) not null,
    status varchar(50) default 'active',
    last_checked timestamp with time zone default now(),
    clicks integer default 0,
    revenue decimal(10,2) default 0.0,
    user_id uuid references users(id) on delete cascade,
    last_status integer,
    status_reason text,
    created_at timestamp with time zone default now(),
    updated_at timestamp with time zone default now()
);

-- Alerts table
create table alerts (
    id uuid primary key default uuid_generate_v4(),
    type varchar(50) not null,
    message text not null,
    read boolean default false,
    user_id uuid references users(id) on delete cascade,
    link_id uuid references links(id) on delete set null,
    created_at timestamp with time zone default now()
);

-- Alert Settings table
create table alert_settings (
    user_id uuid primary key references users(id) on delete cascade,
    email_notifications boolean default true,
    broken_links boolean default true,
    price_changes boolean default true,
    monthly_reports boolean default true,
    updated_at timestamp with time zone default now()
);

-- Notification Queue table
create table notification_queue (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid references users(id) on delete cascade,
    type varchar(50) not null,
    title varchar(255) not null,
    message text not null,
    status varchar(50) default 'pending',
    scheduled_for timestamp with time zone default now(),
    created_at timestamp with time zone default now(),
    processed_at timestamp with time zone
);

-- Create update_timestamp function
create or replace function update_timestamp()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

-- Create triggers for updated_at
create trigger update_users_timestamp
    before update on users
    for each row
    execute function update_timestamp();

create trigger update_links_timestamp
    before update on links
    for each row
    execute function update_timestamp();

-- Create index for faster queries
create index idx_links_user_id on links(user_id);
create index idx_alerts_user_id on alerts(user_id);
create index idx_alerts_link_id on alerts(link_id);
create index idx_notification_queue_status on notification_queue(status);
create index idx_notification_queue_scheduled_for on notification_queue(scheduled_for);