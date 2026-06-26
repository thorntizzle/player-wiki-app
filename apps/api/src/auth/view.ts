import type { ApiConfig } from "../config.js";
import type { CampaignViewModel } from "../campaigns/view.js";
import type { FixtureSystemsRole } from "../systems/sources.js";

const FIXTURE_TIMESTAMP = "2026-06-25T00:00:00+00:00";

interface FixtureUser {
  id: number;
  email: string;
  display_name: string;
  is_admin: boolean;
  status: string;
  created_at: string;
  updated_at: string;
}

function fixtureUser(role: FixtureSystemsRole): FixtureUser {
  if (role === "admin") {
    return {
      id: 1003,
      email: "fixture-admin@example.com",
      display_name: "Fixture Admin",
      is_admin: true,
      status: "active",
      created_at: FIXTURE_TIMESTAMP,
      updated_at: FIXTURE_TIMESTAMP,
    };
  }
  if (role === "dm") {
    return {
      id: 1002,
      email: "fixture-dm@example.com",
      display_name: "Fixture DM",
      is_admin: false,
      status: "active",
      created_at: FIXTURE_TIMESTAMP,
      updated_at: FIXTURE_TIMESTAMP,
    };
  }
  return {
    id: 1001,
    email: "fixture-player@example.com",
    display_name: "Fixture Player",
    is_admin: false,
    status: "active",
    created_at: FIXTURE_TIMESTAMP,
    updated_at: FIXTURE_TIMESTAMP,
  };
}

function viewAsChoice(user: FixtureUser) {
  return {
    id: user.id,
    email: user.email,
    display_name: user.display_name,
    is_admin: user.is_admin,
    status: user.status,
  };
}

function membershipRole(role: FixtureSystemsRole): "player" | "dm" {
  return role === "player" ? "player" : "dm";
}

export function buildFixtureMePayload(config: ApiConfig, campaigns: CampaignViewModel[], role: FixtureSystemsRole) {
  const user = fixtureUser(role);
  const userChoices = role === "admin" ? [viewAsChoice(fixtureUser("player")), viewAsChoice(fixtureUser("dm"))] : [];
  return {
    ok: true,
    app: {
      ...config.app,
      db_path: config.dbPath,
      campaigns_dir: config.campaignsDir,
    },
    auth_source: "fixture",
    user,
    memberships: campaigns.map((campaign, index) => ({
      id: 2000 + index,
      campaign_slug: campaign.slug,
      role: membershipRole(role),
      status: "active",
      created_at: FIXTURE_TIMESTAMP,
      updated_at: FIXTURE_TIMESTAMP,
    })),
    preferences: {
      theme_key: "parchment",
      session_chat_order: "newest_first",
      frontend_mode: "gen2",
    },
    view_as: {
      can_view_as: role === "admin",
      active_user: null,
      user_choices: userChoices,
    },
  };
}
