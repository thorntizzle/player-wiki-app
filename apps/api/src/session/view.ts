import { createHash } from "node:crypto";

import type { CampaignViewModel } from "../campaigns/view.js";

export const SESSION_READONLY_REVISION = 0;

export interface SessionPermissionBlock {
  can_manage_session: false;
  can_post_messages: false;
}

export interface SessionStatePayload {
  ok: true;
  campaign: CampaignViewModel;
  permissions: SessionPermissionBlock;
  active_session: null;
  messages: [];
  session_message_recipient_player_choices: [];
  show_session_dm_passive_scores: false;
  session_revision: number;
  session_view_token: string;
}

function stableHexDigest(value: string): string {
  return createHash("sha1").update(value).digest("hex");
}

export function buildSessionViewToken(campaign: CampaignViewModel, sessionRevision: number): string {
  const rawToken = [
    "fixture-read-only-session-state-v1",
    campaign.slug,
    campaign.system,
    String(campaign.current_session ?? ""),
    String(sessionRevision),
  ].join("|");
  return stableHexDigest(rawToken).slice(0, 12);
}

export function buildSessionStatePayload(campaign: CampaignViewModel): SessionStatePayload {
  const sessionRevision = SESSION_READONLY_REVISION;
  return {
    ok: true,
    campaign,
    permissions: {
      can_manage_session: false,
      can_post_messages: false,
    },
    active_session: null,
    messages: [],
    session_message_recipient_player_choices: [],
    show_session_dm_passive_scores: false,
    session_revision: sessionRevision,
    session_view_token: buildSessionViewToken(campaign, sessionRevision),
  };
}
