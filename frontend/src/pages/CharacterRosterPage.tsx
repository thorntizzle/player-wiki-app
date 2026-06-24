import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "@tanstack/react-router";
import type { FormEvent } from "react";

import { getApiErrorMessage } from "../apiErrors";
import { useApiClient } from "../apiClientContext";
import { ApiErrorNotice } from "../components/feedback";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";

export function CharacterRosterPage() {
  const { campaignSlug } = useParams({
    from: "/campaigns/$campaignSlug/characters/",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const initialQuery = new URLSearchParams(window.location.search).get("q") || "";
  const [searchDraft, setSearchDraft] = useState(initialQuery);
  const [submittedQuery, setSubmittedQuery] = useState(initialQuery);

  const rosterQuery = useQuery({
    queryKey: ["characters", resolvedCampaignSlug, submittedQuery],
    queryFn: () => apiClient.getCharacters(resolvedCampaignSlug, submittedQuery),
    enabled: Boolean(resolvedCampaignSlug),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(rosterQuery.error)) {
      setAuthRequired(true);
    }
  }, [rosterQuery.error, setAuthRequired]);

  const data = rosterQuery.data;
  const characters = data?.characters ?? [];
  const error = getApiErrorMessage(rosterQuery.error);
  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextQuery = searchDraft.trim();
    const nextUrl = nextQuery
      ? `/app-next/campaigns/${encodeURIComponent(resolvedCampaignSlug)}/characters?q=${encodeURIComponent(nextQuery)}`
      : `/app-next/campaigns/${encodeURIComponent(resolvedCampaignSlug)}/characters`;
    window.history.pushState(null, "", nextUrl);
    setSubmittedQuery(nextQuery);
  };
  const hasCreateCharacterLink = Boolean(data?.links?.create_character_url);
  const shouldShowRosterToolsHeading =
    hasCreateCharacterLink || data?.tools?.native_character_create_supported === false;
  const characterCreateLane = data?.tools?.character_create_lane;
  const rosterMeta = hasCreateCharacterLink
    ? characterCreateLane === "xianxia"
      ? "Use the Xianxia character creator to start new native character records directly in the app."
      : "Use the current PHB level 1 builder to create new characters directly in the app."
    : "Native character creation and progression stay hidden here for campaigns outside the current DND-5E in-app toolset.";
  const rosterLede =
    characterCreateLane === "dnd5e"
      ? "Open a player sheet in read mode for play, or start a new in-app PHB level 1 character when you need native sheet data instead of an imported PDF."
      : characterCreateLane === "xianxia"
      ? "Open a player sheet in read mode for play, or start a new native Xianxia character record for this campaign."
      : "Open a player sheet for read mode, use inline state controls when authorized, and use Advanced Editor for larger sheet changes.";

  return (
    <>
      <section className="hero compact character-roster-hero">
        <p className="eyebrow">Character roster</p>
        <h1>Characters</h1>
        <p className="lede">{rosterLede}</p>
      </section>
      <ApiErrorNotice isLoading={rosterQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      <section className="card search-card character-roster-tools">
        {shouldShowRosterToolsHeading ? (
          <div className="section-heading">
            <div>
              <h2>{hasCreateCharacterLink ? "Roster tools" : "Roster"}</h2>
              <p className="meta">{rosterMeta}</p>
            </div>
            {data?.links?.create_character_url ? (
              <a className="button-link" href={data.links.create_character_url}>
                Create character
              </a>
            ) : null}
            {data?.links?.import_xianxia_url ? (
              <a className="button-link" href={data.links.import_xianxia_url}>
                Import existing character
              </a>
            ) : null}
          </div>
        ) : null}
        <form className="search-form character-roster-search" onSubmit={submitSearch}>
          <input
            type="search"
            value={searchDraft}
            onChange={(event) => setSearchDraft(event.currentTarget.value)}
            placeholder="Search characters by name, class, species, or background"
            aria-label="Search characters"
          />
          <button type="submit">Search</button>
        </form>
        {data ? (
          <p className="meta">
            {data.result_count ?? characters.length} character{(data.result_count ?? characters.length) === 1 ? "" : "s"} visible
          </p>
        ) : null}
      </section>
      {data ? (
        <>
          {characters.length ? (
            <section className="grid">
              {characters.map((character) => (
                <article className="card character-card" key={character.slug}>
                  <div className="character-card__top">
                    {character.portrait ? (
                      <img className="character-card__portrait" src={character.portrait.url} alt={character.portrait.alt_text || character.name} />
                    ) : null}
                    <div>
                      <p className="card-kicker">{character.class_level_text || character.system || "Character"}</p>
                      <h2>
                        <a href={character.href || `/app-next/campaigns/${encodeURIComponent(resolvedCampaignSlug)}/characters/${encodeURIComponent(character.slug)}`}>
                          {character.name}
                        </a>
                      </h2>
                      <p className="character-card__meta">
                        {[character.species, character.background].filter(Boolean).join(" · ") || character.status}
                      </p>
                    </div>
                  </div>
                  <div className="character-card__stats">
                    <div>
                      <span className="meta">HP</span>
                      <strong>
                        {character.current_hp} / {character.max_hp}
                      </strong>
                    </div>
                    <div>
                      <span className="meta">Temp HP</span>
                      <strong>{character.temp_hp}</strong>
                    </div>
                    {character.hit_dice?.value ? (
                      <div>
                        <span className="meta">Hit Dice</span>
                        <strong>{character.hit_dice.value}</strong>
                      </div>
                    ) : null}
                  </div>
                  {character.resource_preview?.length ? (
                    <ul className="plain-list resource-preview-list">
                      {character.resource_preview.map((resource) => (
                        <li key={`${character.slug}-${resource.label}`}>
                          <span>{resource.label}</span>
                          <strong>{resource.value}</strong>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  <a
                    className="button-link"
                    href={
                      character.href || `/app-next/campaigns/${encodeURIComponent(resolvedCampaignSlug)}/characters/${encodeURIComponent(character.slug)}`
                    }
                  >
                    Open sheet
                  </a>
                </article>
              ))}
            </section>
          ) : (
            <section className="card">
              <h2>{submittedQuery ? "No matching characters" : "No visible characters yet"}</h2>
              <p>{submittedQuery ? "Try a broader search term or clear the current filter." : "This campaign does not currently have any active player sheets available in the app."}</p>
            </section>
          )}
        </>
      ) : null}
    </>
  );
}
