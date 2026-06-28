# TypeScript Backend Rewrite - Route Snapshots

Last updated: 2026-06-28

Status: documentation review companion for executable source-of-truth fixtures

This file records source-derived route snapshots and fixture-backed missing-resource
response shapes for the TypeScript backend rewrite.

This file is the human-review companion to:

- `docs/typescript-backend-rewrite/route-snapshots.json`
- `scripts/route_snapshots.py`

`route-snapshots.json` is the executable source-of-truth artifact for route declaration
drift checks. Use the command below after route edits to regenerate it.

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\route_snapshots.py --write
```

Check parity as part of CI or local validation:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\route_snapshots.py --check
```

## Snapshot Decision

These fixtures are generated from source by AST parser so route inventory stays
declarative and deterministic for parity checks.

## Source Snapshot Command

The executable parser command above replaced regex-based extraction in this document.
No manual grep snippets are expected to be maintained here.

## `/api/v1` Route Snapshot

Count: 135 declarations: 46 `GET`, 39 `POST`, 21 `PATCH`, 11 `PUT`, 18 `DELETE`.

```text
GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/advanced-editor # player_wiki/api.py:3297
PUT /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/advanced-editor # player_wiki/api.py:3319
GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/retraining # player_wiki/api.py:3691
POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/retraining # player_wiki/api.py:3707
GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/level-up # player_wiki/api.py:3971
POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/level-up # player_wiki/api.py:3999
GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/progression-repair # player_wiki/api.py:4241
POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/progression-repair # player_wiki/api.py:4270
GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/cultivation # player_wiki/api.py:4679
POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/cultivation # player_wiki/api.py:4688
GET /api/v1/me # player_wiki/api.py:5230
POST /api/v1/me/view-as # player_wiki/api.py:5252
DELETE /api/v1/me/view-as # player_wiki/api.py:5287
GET /api/v1/me/settings # player_wiki/api.py:5298
PATCH /api/v1/me/settings # player_wiki/api.py:5320
GET /api/v1/admin # player_wiki/api.py:5384
GET /api/v1/admin/users/<int:user_id> # player_wiki/api.py:5390
POST /api/v1/admin/users/invite # player_wiki/api.py:5397
POST /api/v1/admin/users/<int:user_id>/membership # player_wiki/api.py:5486
DELETE /api/v1/admin/users/<int:user_id>/membership # player_wiki/api.py:5529
POST /api/v1/admin/users/<int:user_id>/assignment # player_wiki/api.py:5570
DELETE /api/v1/admin/users/<int:user_id>/assignment # player_wiki/api.py:5626
POST /api/v1/admin/users/<int:user_id>/invite # player_wiki/api.py:5667
POST /api/v1/admin/users/<int:user_id>/password-reset # player_wiki/api.py:5694
POST /api/v1/admin/users/<int:user_id>/disable # player_wiki/api.py:5721
POST /api/v1/admin/users/<int:user_id>/enable # player_wiki/api.py:5749
DELETE /api/v1/admin/users/<int:user_id> # player_wiki/api.py:5783
GET /api/v1/app # player_wiki/api.py:5829
GET /api/v1/systems/import-runs # player_wiki/api.py:5833
GET /api/v1/systems/import-runs/<int:import_run_id> # player_wiki/api.py:5857
POST /api/v1/systems/imports/dnd5e # player_wiki/api.py:5866
GET /api/v1/campaigns # player_wiki/api.py:5935
GET /api/v1/campaigns/<campaign_slug> # player_wiki/api.py:5945
GET /api/v1/campaigns/<campaign_slug>/control # player_wiki/api.py:5970
PATCH /api/v1/campaigns/<campaign_slug>/control/visibility # player_wiki/api.py:6009
GET /api/v1/campaigns/<campaign_slug>/help # player_wiki/api.py:6092
GET /api/v1/campaigns/<campaign_slug>/wiki # player_wiki/api.py:6152
GET /api/v1/campaigns/<campaign_slug>/wiki/sections/<section_slug> # player_wiki/api.py:6245
GET /api/v1/campaigns/<campaign_slug>/wiki/pages/<path:page_slug> # player_wiki/api.py:6296
GET /api/v1/campaigns/<campaign_slug>/content/config # player_wiki/api.py:6353
PATCH /api/v1/campaigns/<campaign_slug>/content/config # player_wiki/api.py:6363
GET /api/v1/campaigns/<campaign_slug>/content/assets # player_wiki/api.py:6381
GET /api/v1/campaigns/<campaign_slug>/content/assets/<path:asset_ref> # player_wiki/api.py:6398
PUT /api/v1/campaigns/<campaign_slug>/content/assets/<path:asset_ref> # player_wiki/api.py:6414
DELETE /api/v1/campaigns/<campaign_slug>/content/assets/<path:asset_ref> # player_wiki/api.py:6434
GET /api/v1/campaigns/<campaign_slug>/content/pages # player_wiki/api.py:6458
GET /api/v1/campaigns/<campaign_slug>/content/pages/<path:page_ref> # player_wiki/api.py:6488
PUT /api/v1/campaigns/<campaign_slug>/content/pages/<path:page_ref> # player_wiki/api.py:6527
DELETE /api/v1/campaigns/<campaign_slug>/content/pages/<path:page_ref> # player_wiki/api.py:6575
GET /api/v1/campaigns/<campaign_slug>/content/characters # player_wiki/api.py:6645
GET /api/v1/campaigns/<campaign_slug>/content/characters/<character_slug> # player_wiki/api.py:6660
PUT /api/v1/campaigns/<campaign_slug>/content/characters/<character_slug> # player_wiki/api.py:6672
DELETE /api/v1/campaigns/<campaign_slug>/content/characters/<character_slug> # player_wiki/api.py:6690
GET /api/v1/campaigns/<campaign_slug>/systems # player_wiki/api.py:6719
GET /api/v1/campaigns/<campaign_slug>/systems/search # player_wiki/api.py:6720
GET /api/v1/campaigns/<campaign_slug>/systems/sources # player_wiki/api.py:6736
PUT /api/v1/campaigns/<campaign_slug>/systems/sources # player_wiki/api.py:6760
GET /api/v1/campaigns/<campaign_slug>/systems/sources/<source_id> # player_wiki/api.py:6809
GET /api/v1/campaigns/<campaign_slug>/systems/sources/<source_id>/types/<entry_type> # player_wiki/api.py:6931
GET /api/v1/campaigns/<campaign_slug>/systems/entries/<entry_slug> # player_wiki/api.py:7010
PUT /api/v1/campaigns/<campaign_slug>/systems/overrides/<path:entry_key> # player_wiki/api.py:7057
GET /api/v1/campaigns/<campaign_slug>/session # player_wiki/api.py:7110
GET /api/v1/campaigns/<campaign_slug>/session/article-sources/search # player_wiki/api.py:7134
GET /api/v1/campaigns/<campaign_slug>/session/articles/<int:article_id>/image # player_wiki/api.py:7163
POST /api/v1/campaigns/<campaign_slug>/session/start # player_wiki/api.py:7187
POST /api/v1/campaigns/<campaign_slug>/session/close # player_wiki/api.py:7208
GET /api/v1/campaigns/<campaign_slug>/session/logs/<int:session_id> # player_wiki/api.py:7229
DELETE /api/v1/campaigns/<campaign_slug>/session/logs/<int:session_id> # player_wiki/api.py:7259
POST /api/v1/campaigns/<campaign_slug>/session/messages # player_wiki/api.py:7273
POST /api/v1/campaigns/<campaign_slug>/session/articles # player_wiki/api.py:7308
PUT /api/v1/campaigns/<campaign_slug>/session/articles/<int:article_id> # player_wiki/api.py:7491
POST /api/v1/campaigns/<campaign_slug>/session/articles/<int:article_id>/reveal # player_wiki/api.py:7560
DELETE /api/v1/campaigns/<campaign_slug>/session/articles/<int:article_id> # player_wiki/api.py:7600
DELETE /api/v1/campaigns/<campaign_slug>/session/articles/revealed # player_wiki/api.py:7614
GET /api/v1/campaigns/<campaign_slug>/dm-content # player_wiki/api.py:7641
GET /api/v1/campaigns/<campaign_slug>/dm-content/systems # player_wiki/api.py:7646
POST /api/v1/campaigns/<campaign_slug>/dm-content/statblocks # player_wiki/api.py:7658
PUT /api/v1/campaigns/<campaign_slug>/dm-content/statblocks/<int:statblock_id> # player_wiki/api.py:7687
DELETE /api/v1/campaigns/<campaign_slug>/dm-content/statblocks/<int:statblock_id> # player_wiki/api.py:7734
POST /api/v1/campaigns/<campaign_slug>/dm-content/conditions # player_wiki/api.py:7751
PUT /api/v1/campaigns/<campaign_slug>/dm-content/conditions/<int:condition_definition_id> # player_wiki/api.py:7779
DELETE /api/v1/campaigns/<campaign_slug>/dm-content/conditions/<int:condition_definition_id> # player_wiki/api.py:7819
POST /api/v1/campaigns/<campaign_slug>/systems/custom-entries # player_wiki/api.py:7836
POST /api/v1/campaigns/<campaign_slug>/systems/item-mechanics/import # player_wiki/api.py:7890
PUT /api/v1/campaigns/<campaign_slug>/systems/custom-entries/<entry_slug> # player_wiki/api.py:7939
POST /api/v1/campaigns/<campaign_slug>/systems/custom-entries/<entry_slug>/archive # player_wiki/api.py:7993
POST /api/v1/campaigns/<campaign_slug>/systems/custom-entries/<entry_slug>/restore # player_wiki/api.py:8032
GET /api/v1/campaigns/<campaign_slug>/combat # player_wiki/api.py:8071
GET /api/v1/campaigns/<campaign_slug>/combat/live-state # player_wiki/api.py:8089
GET /api/v1/campaigns/<campaign_slug>/combat/systems-monsters/search # player_wiki/api.py:8107
POST /api/v1/campaigns/<campaign_slug>/combat/player-combatants # player_wiki/api.py:8171
POST /api/v1/campaigns/<campaign_slug>/combat/npc-combatants # player_wiki/api.py:8197
POST /api/v1/campaigns/<campaign_slug>/combat/statblock-combatants # player_wiki/api.py:8229
POST /api/v1/campaigns/<campaign_slug>/combat/systems-monsters # player_wiki/api.py:8281
POST /api/v1/campaigns/<campaign_slug>/combat/advance-turn # player_wiki/api.py:8333
POST /api/v1/campaigns/<campaign_slug>/combat/clear # player_wiki/api.py:8355
POST /api/v1/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/set-current # player_wiki/api.py:8377
PATCH /api/v1/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/turn # player_wiki/api.py:8400
PATCH /api/v1/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/vitals # player_wiki/api.py:8438
PATCH /api/v1/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/resources # player_wiki/api.py:8500
PATCH /api/v1/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/npc-resources # player_wiki/api.py:8549
POST /api/v1/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/conditions # player_wiki/api.py:8594
DELETE /api/v1/campaigns/<campaign_slug>/combat/conditions/<int:condition_id> # player_wiki/api.py:8620
DELETE /api/v1/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id> # player_wiki/api.py:8635
GET /api/v1/campaigns/<campaign_slug>/characters # player_wiki/api.py:8650
GET /api/v1/campaigns/<campaign_slug>/characters/create # player_wiki/api.py:8689
POST /api/v1/campaigns/<campaign_slug>/characters/create # player_wiki/api.py:8696
GET /api/v1/campaigns/<campaign_slug>/characters/import/xianxia-manual # player_wiki/api.py:8780
POST /api/v1/campaigns/<campaign_slug>/characters/import/xianxia-manual # player_wiki/api.py:8802
GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug> # player_wiki/api.py:8872
POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/controls/assignment # player_wiki/api.py:8918
DELETE /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/controls/assignment # player_wiki/api.py:8969
DELETE /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/controls # player_wiki/api.py:9011
PUT /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/portrait # player_wiki/api.py:9066
DELETE /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/portrait # player_wiki/api.py:9119
GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/rest-preview/<rest_type> # player_wiki/api.py:9166
PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/sheet-edit # player_wiki/api.py:9382
PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/vitals # player_wiki/api.py:9409
PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/resources/<resource_id> # player_wiki/api.py:9436
PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/spell-slots/<int:level> # player_wiki/api.py:9452
PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/inventory/<item_id> # player_wiki/api.py:9469
PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-active-state # player_wiki/api.py:9570
POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-dao-immolating-use-requests # player_wiki/api.py:9585
POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-dao-immolating-use-records # player_wiki/api.py:9615
POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory # player_wiki/api.py:9649
PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/<item_id> # player_wiki/api.py:9663
DELETE /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/<item_id> # player_wiki/api.py:9678
PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/<item_id>/equipped # player_wiki/api.py:9692
PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/equipment/<item_id> # player_wiki/api.py:9707
PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/artificer-infusions # player_wiki/api.py:9723
PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/feature-states/<feature_key> # player_wiki/api.py:9741
PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/currency # player_wiki/api.py:9756
PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/notes # player_wiki/api.py:9782
PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/personal # player_wiki/api.py:9796
POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/rest/<rest_type> # player_wiki/api.py:9812
```

## Flask Browser Compatibility Route Snapshot

Human-readable count: 138 declarations: 49 `GET`, 82 `POST`, 7 `GET,POST` dual-method form routes.

Executable JSON count: 145 expanded route entries: 56 `GET`, 89 `POST`.

```text
GET /app-next # player_wiki/app.py:1432
GET /app-next/ # player_wiki/app.py:1433
GET /app-next/<path:asset_path> # player_wiki/app.py:1439
GET /healthz # player_wiki/app.py:9209
GET / # player_wiki/app.py:9226
GET /campaigns/<campaign_slug> # player_wiki/app.py:9250
GET /campaigns/<campaign_slug>/global-search # player_wiki/app.py:9289
GET /campaigns/<campaign_slug>/global-search/preview # player_wiki/app.py:9313
GET /campaigns/<campaign_slug>/help # player_wiki/app.py:9343
GET /campaigns/<campaign_slug>/assets/<path:asset_path> # player_wiki/app.py:9349
GET /campaigns/<campaign_slug>/sections/<section_slug> # player_wiki/app.py:9367
GET /campaigns/<campaign_slug>/pages/<path:page_slug> # player_wiki/app.py:9405
GET /campaigns/<campaign_slug>/control-panel # player_wiki/app.py:9442
POST /campaigns/<campaign_slug>/control-panel/visibility # player_wiki/app.py:9452
GET /campaigns/<campaign_slug>/systems # player_wiki/app.py:9517
GET /campaigns/<campaign_slug>/systems/search # player_wiki/app.py:9529
GET /campaigns/<campaign_slug>/systems/sources/<source_id> # player_wiki/app.py:9541
GET /campaigns/<campaign_slug>/systems/sources/<source_id>/types/<entry_type> # player_wiki/app.py:9552
GET /campaigns/<campaign_slug>/systems/entries/<entry_slug> # player_wiki/app.py:9564
GET /campaigns/<campaign_slug>/systems/control-panel # player_wiki/app.py:9570
POST /campaigns/<campaign_slug>/systems/control-panel/sources # player_wiki/app.py:9579
POST /campaigns/<campaign_slug>/systems/control-panel/shared-core-permission # player_wiki/app.py:9660
POST /campaigns/<campaign_slug>/systems/control-panel/overrides # player_wiki/app.py:9720
GET /campaigns/<campaign_slug>/systems/control-panel/shared-entries/<entry_slug>/edit # player_wiki/app.py:9867
POST /campaigns/<campaign_slug>/systems/control-panel/shared-entries/<entry_slug> # player_wiki/app.py:9876
POST /campaigns/<campaign_slug>/systems/control-panel/custom-entries # player_wiki/app.py:9973
GET /campaigns/<campaign_slug>/systems/control-panel/custom-entries/<entry_slug>/edit # player_wiki/app.py:10025
POST /campaigns/<campaign_slug>/systems/control-panel/custom-entries/<entry_slug> # player_wiki/app.py:10041
POST /campaigns/<campaign_slug>/systems/control-panel/custom-entries/<entry_slug>/archive # player_wiki/app.py:10099
POST /campaigns/<campaign_slug>/systems/control-panel/custom-entries/<entry_slug>/restore # player_wiki/app.py:10141
POST /campaigns/<campaign_slug>/systems/control-panel/imports/dnd5e # player_wiki/app.py:10183
GET /campaigns/<campaign_slug>/dm-content # player_wiki/app.py:10312
GET /campaigns/<campaign_slug>/dm-content/<dm_content_subpage> # player_wiki/app.py:10318
GET /campaigns/<campaign_slug>/dm-content/player-wiki/pages/<path:page_ref>/edit # player_wiki/app.py:10332
GET /campaigns/<campaign_slug>/dm-content/player-wiki/session-articles/<int:article_id>/new # player_wiki/app.py:10357
POST /campaigns/<campaign_slug>/dm-content/player-wiki/pages # player_wiki/app.py:10393
POST /campaigns/<campaign_slug>/dm-content/player-wiki/pages/<path:page_ref> # player_wiki/app.py:10482
POST /campaigns/<campaign_slug>/dm-content/player-wiki/pages/<path:page_ref>/unpublish # player_wiki/app.py:10554
POST /campaigns/<campaign_slug>/dm-content/player-wiki/pages/<path:page_ref>/delete # player_wiki/app.py:10603
POST /campaigns/<campaign_slug>/dm-content/staged-articles # player_wiki/app.py:10686
POST /campaigns/<campaign_slug>/dm-content/staged-articles/<int:article_id> # player_wiki/app.py:10721
POST /campaigns/<campaign_slug>/dm-content/staged-articles/<int:article_id>/delete # player_wiki/app.py:10748
POST /campaigns/<campaign_slug>/dm-content/statblocks # player_wiki/app.py:10782
POST /campaigns/<campaign_slug>/dm-content/statblocks/<int:statblock_id> # player_wiki/app.py:10827
POST /campaigns/<campaign_slug>/dm-content/statblocks/<int:statblock_id>/delete # player_wiki/app.py:10884
POST /campaigns/<campaign_slug>/dm-content/conditions # player_wiki/app.py:10903
POST /campaigns/<campaign_slug>/dm-content/conditions/<int:condition_definition_id> # player_wiki/app.py:10931
POST /campaigns/<campaign_slug>/dm-content/conditions/<int:condition_definition_id>/delete # player_wiki/app.py:10980
GET /campaigns/<campaign_slug>/combat # player_wiki/app.py:11002
GET /campaigns/<campaign_slug>/combat/live-state # player_wiki/app.py:11016
GET /campaigns/<campaign_slug>/combat/dm # player_wiki/app.py:11060
GET /campaigns/<campaign_slug>/combat/dm/live-state # player_wiki/app.py:11079
GET /campaigns/<campaign_slug>/combat/status # player_wiki/app.py:11147
GET /campaigns/<campaign_slug>/combat/status/live-state # player_wiki/app.py:11153
GET /campaigns/<campaign_slug>/combat/character # player_wiki/app.py:11214
GET /campaigns/<campaign_slug>/combat/character/live-state # player_wiki/app.py:11226
POST /campaigns/<campaign_slug>/combat/character/combatants/<int:combatant_id>/resources/<resource_id> # player_wiki/app.py:11268
POST /campaigns/<campaign_slug>/combat/character/combatants/<int:combatant_id>/spell-slots/<int:level> # player_wiki/app.py:11290
POST /campaigns/<campaign_slug>/combat/character/combatants/<int:combatant_id>/equipment/<item_id>/state # player_wiki/app.py:11318
POST /campaigns/<campaign_slug>/combat/character/combatants/<int:combatant_id>/feature-states/<feature_key> # player_wiki/app.py:11340
GET /campaigns/<campaign_slug>/combat/systems-monsters/search # player_wiki/app.py:11361
POST /campaigns/<campaign_slug>/combat/player-combatants # player_wiki/app.py:11423
POST /campaigns/<campaign_slug>/combat/npc-combatants # player_wiki/app.py:11460
POST /campaigns/<campaign_slug>/combat/statblock-combatants # player_wiki/app.py:11502
POST /campaigns/<campaign_slug>/combat/systems-monsters # player_wiki/app.py:11575
POST /campaigns/<campaign_slug>/combat/advance-turn # player_wiki/app.py:11640
POST /campaigns/<campaign_slug>/combat/clear # player_wiki/app.py:11678
POST /campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/set-current # player_wiki/app.py:11712
POST /campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/turn # player_wiki/app.py:11747
POST /campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/vitals # player_wiki/app.py:11788
POST /campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/resources # player_wiki/app.py:11867
POST /campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/player-detail-visibility # player_wiki/app.py:11919
POST /campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/conditions # player_wiki/app.py:11959
POST /campaigns/<campaign_slug>/combat/conditions/<int:condition_id>/delete # player_wiki/app.py:11996
POST /campaigns/<campaign_slug>/combat/conditions/<int:condition_id> # player_wiki/app.py:12025
POST /campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/delete # player_wiki/app.py:12064
GET /campaigns/<campaign_slug>/session # player_wiki/app.py:12091
GET /campaigns/<campaign_slug>/session/dm # player_wiki/app.py:12097
GET /campaigns/<campaign_slug>/session/character # player_wiki/app.py:12106
GET /campaigns/<campaign_slug>/session/live-state # player_wiki/app.py:12119
GET /campaigns/<campaign_slug>/session/article-sources/search # player_wiki/app.py:12161
GET /campaigns/<campaign_slug>/session/wiki-lookup/search # player_wiki/app.py:12188
GET /campaigns/<campaign_slug>/session/wiki-lookup/preview # player_wiki/app.py:12220
GET /campaigns/<campaign_slug>/session-article-images/<int:article_id> # player_wiki/app.py:12258
POST /campaigns/<campaign_slug>/session/start # player_wiki/app.py:12283
POST /campaigns/<campaign_slug>/session/messages # player_wiki/app.py:12312
POST /campaigns/<campaign_slug>/session/articles # player_wiki/app.py:12346
POST /campaigns/<campaign_slug>/session/articles/<int:article_id> # player_wiki/app.py:12384
GET /campaigns/<campaign_slug>/session/articles/<int:article_id>/convert # player_wiki/app.py:12414
POST /campaigns/<campaign_slug>/session/articles/<int:article_id>/convert # player_wiki/app.py:12423
POST /campaigns/<campaign_slug>/session/articles/<int:article_id>/reveal # player_wiki/app.py:12492
POST /campaigns/<campaign_slug>/session/articles/<int:article_id>/delete # player_wiki/app.py:12523
POST /campaigns/<campaign_slug>/session/articles/clear-revealed # player_wiki/app.py:12565
POST /campaigns/<campaign_slug>/session/close # player_wiki/app.py:12602
GET /campaigns/<campaign_slug>/session/logs/<int:session_id> # player_wiki/app.py:12630
POST /campaigns/<campaign_slug>/session/logs/<int:session_id>/delete # player_wiki/app.py:12668
GET /campaigns/<campaign_slug>/characters # player_wiki/app.py:12691
GET,POST /campaigns/<campaign_slug>/characters/new # player_wiki/app.py:12731
GET,POST /campaigns/<campaign_slug>/characters/import/xianxia-manual # player_wiki/app.py:12858
GET,POST /campaigns/<campaign_slug>/characters/<character_slug>/level-up # player_wiki/app.py:12918
GET,POST /campaigns/<campaign_slug>/characters/<character_slug>/cultivation # player_wiki/app.py:13021
GET,POST /campaigns/<campaign_slug>/characters/<character_slug>/progression-repair # player_wiki/app.py:13348
GET,POST /campaigns/<campaign_slug>/characters/<character_slug>/edit # player_wiki/app.py:13475
GET,POST /campaigns/<campaign_slug>/characters/<character_slug>/retraining # player_wiki/app.py:13635
GET /campaigns/<campaign_slug>/characters/<character_slug> # player_wiki/app.py:13806
POST /campaigns/<campaign_slug>/characters/<character_slug>/controls/assignment # player_wiki/app.py:13811
POST /campaigns/<campaign_slug>/characters/<character_slug>/controls/assignment/remove # player_wiki/app.py:13856
POST /campaigns/<campaign_slug>/characters/<character_slug>/controls/delete # player_wiki/app.py:13891
GET /campaigns/<campaign_slug>/characters/<character_slug>/equipment/systems-items/search # player_wiki/app.py:13936
GET /campaigns/<campaign_slug>/characters/<character_slug>/spellcasting/spells/search # player_wiki/app.py:13986
POST /campaigns/<campaign_slug>/characters/<character_slug>/spellcasting/add # player_wiki/app.py:14019
POST /campaigns/<campaign_slug>/characters/<character_slug>/spellcasting/update # player_wiki/app.py:14057
POST /campaigns/<campaign_slug>/characters/<character_slug>/spellcasting/remove # player_wiki/app.py:14095
POST /campaigns/<campaign_slug>/characters/<character_slug>/equipment/add-systems # player_wiki/app.py:14132
POST /campaigns/<campaign_slug>/characters/<character_slug>/equipment/add-manual # player_wiki/app.py:14173
POST /campaigns/<campaign_slug>/characters/<character_slug>/equipment/add-campaign-item # player_wiki/app.py:14195
POST /campaigns/<campaign_slug>/characters/<character_slug>/equipment/<item_id>/update # player_wiki/app.py:14226
POST /campaigns/<campaign_slug>/characters/<character_slug>/equipment/<item_id>/state # player_wiki/app.py:14277
POST /campaigns/<campaign_slug>/characters/<character_slug>/feature-states/<feature_key> # player_wiki/app.py:14298
POST /campaigns/<campaign_slug>/characters/<character_slug>/equipment/<item_id>/remove # player_wiki/app.py:14407
POST /campaigns/<campaign_slug>/characters/<character_slug>/xianxia/dao-immolating-use-requests # player_wiki/app.py:14426
POST /campaigns/<campaign_slug>/characters/<character_slug>/xianxia/dao-immolating-use-records # player_wiki/app.py:14462
GET /campaigns/<campaign_slug>/characters/<character_slug>/portrait # player_wiki/app.py:14500
POST /campaigns/<campaign_slug>/characters/<character_slug>/personal/portrait # player_wiki/app.py:14516
POST /campaigns/<campaign_slug>/characters/<character_slug>/personal/portrait/remove # player_wiki/app.py:14583
POST /campaigns/<campaign_slug>/characters/<character_slug>/session/vitals # player_wiki/app.py:14633
POST /campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-active-state # player_wiki/app.py:14662
POST /campaigns/<campaign_slug>/characters/<character_slug>/session/resources/<resource_id> # player_wiki/app.py:14716
POST /campaigns/<campaign_slug>/characters/<character_slug>/session/spell-slots/<int:level> # player_wiki/app.py:14738
POST /campaigns/<campaign_slug>/characters/<character_slug>/session/inventory/<item_id> # player_wiki/app.py:14770
POST /campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/add # player_wiki/app.py:14804
POST /campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/<item_id>/update # player_wiki/app.py:14820
POST /campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/<item_id>/remove # player_wiki/app.py:14837
POST /campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/<item_id>/equipped # player_wiki/app.py:14853
POST /campaigns/<campaign_slug>/characters/<character_slug>/session/currency # player_wiki/app.py:14870
POST /campaigns/<campaign_slug>/characters/<character_slug>/session/notes # player_wiki/app.py:14899
POST /campaigns/<campaign_slug>/characters/<character_slug>/session/personal # player_wiki/app.py:14965
POST /campaigns/<campaign_slug>/characters/<character_slug>/session/rest/<rest_type> # player_wiki/app.py:15049
```

## Missing-Resource Response Shape Snapshot

Probe command: fixture-backed Flask test client using the sanitized test campaign
builder, bearer tokens, and repo venv. Paths below are normalized to placeholders.

Important finding: many `/api/v1` missing-resource responses currently return the
generic Flask HTML 404 page with `text/html`, even when the request sends
`Accept: application/json`. TypeScript parity tests should capture this before
deciding whether a later API-version break should normalize them to JSON.

| Method | Normalized path | Role | Status | Content type | Shape | Error code | Message |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/api/v1/campaigns/<missing_campaign_slug>` | `dm` | `404` | `text/html` | `html/text` | `` | Generic Flask HTML 404 page |
| `GET` | `/api/v1/campaigns/<campaign_slug>/wiki/sections/missing-section` | `player` | `404` | `text/html` | `html/text` | `` | Generic Flask HTML 404 page |
| `GET` | `/api/v1/campaigns/<campaign_slug>/wiki/pages/missing/page` | `player` | `404` | `text/html` | `html/text` | `` | Generic Flask HTML 404 page |
| `GET` | `/api/v1/campaigns/<campaign_slug>/content/assets/missing.txt` | `dm` | `404` | `text/html` | `html/text` | `` | Generic Flask HTML 404 page |
| `GET` | `/api/v1/campaigns/<campaign_slug>/content/pages/missing/page` | `dm` | `404` | `text/html` | `html/text` | `` | Generic Flask HTML 404 page |
| `GET` | `/api/v1/campaigns/<campaign_slug>/content/characters/missing-character` | `dm` | `404` | `text/html` | `html/text` | `` | Generic Flask HTML 404 page |
| `GET` | `/api/v1/campaigns/<campaign_slug>/systems/sources/MISSING` | `dm` | `403` | `application/json` | `json` | `forbidden` | You do not have access to this systems source. |
| `GET` | `/api/v1/campaigns/<campaign_slug>/systems/sources/MISSING/types/monster` | `dm` | `403` | `application/json` | `json` | `forbidden` | You do not have access to this systems source. |
| `GET` | `/api/v1/campaigns/<campaign_slug>/systems/entries/missing-entry` | `dm` | `403` | `application/json` | `json` | `forbidden` | You do not have access to this systems entry. |
| `GET` | `/api/v1/campaigns/<campaign_slug>/session/articles/999999/image` | `player` | `404` | `text/html` | `html/text` | `` | Generic Flask HTML 404 page |
| `GET` | `/api/v1/campaigns/<campaign_slug>/session/logs/999999` | `dm` | `404` | `text/html` | `html/text` | `` | Generic Flask HTML 404 page |
| `PUT` | `/api/v1/campaigns/<campaign_slug>/session/articles/999999` | `dm` | `400` | `application/json` | `json` | `validation_error` | That session article could not be found. |
| `PUT` | `/api/v1/campaigns/<campaign_slug>/dm-content/statblocks/999999` | `dm` | `400` | `application/json` | `json` | `validation_error` | That statblock could not be found. |
| `PUT` | `/api/v1/campaigns/<campaign_slug>/dm-content/conditions/999999` | `dm` | `400` | `application/json` | `json` | `validation_error` | That custom condition could not be found. |
| `PATCH` | `/api/v1/campaigns/<campaign_slug>/combat/combatants/999999/vitals` | `dm` | `404` | `text/html` | `html/text` | `` | Generic Flask HTML 404 page |
| `PATCH` | `/api/v1/campaigns/<campaign_slug>/combat/combatants/999999/resources` | `dm` | `404` | `text/html` | `html/text` | `` | Generic Flask HTML 404 page |
| `DELETE` | `/api/v1/campaigns/<campaign_slug>/combat/combatants/999999` | `dm` | `400` | `application/json` | `json` | `validation_error` | That combatant could not be found. |
| `GET` | `/api/v1/campaigns/<campaign_slug>/characters/missing-character` | `dm` | `404` | `text/html` | `html/text` | `` | Generic Flask HTML 404 page |
| `GET` | `/api/v1/campaigns/<campaign_slug>/characters/missing-character/advanced-editor` | `dm` | `404` | `text/html` | `html/text` | `` | Generic Flask HTML 404 page |
| `GET` | `/api/v1/campaigns/<campaign_slug>/characters/missing-character/retraining` | `dm` | `404` | `text/html` | `html/text` | `` | Generic Flask HTML 404 page |
| `GET` | `/api/v1/campaigns/<campaign_slug>/characters/missing-character/level-up` | `dm` | `404` | `text/html` | `html/text` | `` | Generic Flask HTML 404 page |
| `GET` | `/api/v1/campaigns/<campaign_slug>/characters/missing-character/progression-repair` | `dm` | `404` | `text/html` | `html/text` | `` | Generic Flask HTML 404 page |
| `GET` | `/api/v1/campaigns/<campaign_slug>/characters/missing-character/cultivation` | `dm` | `404` | `text/html` | `html/text` | `` | Generic Flask HTML 404 page |
| `PUT` | `/api/v1/campaigns/<campaign_slug>/characters/missing-character/portrait` | `dm` | `404` | `text/html` | `html/text` | `` | Generic Flask HTML 404 page |
| `PATCH` | `/api/v1/campaigns/<campaign_slug>/characters/missing-character/session/vitals` | `dm` | `404` | `text/html` | `html/text` | `` | Generic Flask HTML 404 page |
| `POST` | `/api/v1/campaigns/<campaign_slug>/characters/missing-character/session/rest/long` | `dm` | `404` | `text/html` | `html/text` | `` | Generic Flask HTML 404 page |

### TypeScript JSON Boundary For Publishing/Content

The 2026-06-28 `rewrite/ts-error-shape-parity-matrix` slice promotes the
published wiki/content asset family from an observed Flask-only matrix entry to
an executable Flask-vs-TypeScript boundary test. Flask remains the production
authority and still serves generic `text/html` 404 pages for these missing
resources even with `Accept: application/json`; the TypeScript candidate keeps
structured JSON 404 envelopes for the fixture API surface:

| Method | Normalized path | Role | Flask shape | TypeScript shape | TypeScript error code |
| --- | --- | --- | --- | --- | --- |
| `GET` | `/api/v1/campaigns/<campaign_slug>/wiki/sections/missing-section` | `player` | `404 text/html` generic page | `404 application/json` | `wiki_section_not_found` |
| `GET` | `/api/v1/campaigns/<campaign_slug>/wiki/pages/missing-page` | `player` | `404 text/html` generic page | `404 application/json` | `wiki_page_not_found` |
| `GET` | `/api/v1/campaigns/<campaign_slug>/content/pages/missing-page` | `dm` | `404 text/html` generic page | `404 application/json` | `content_page_not_found` |
| `GET` | `/api/v1/campaigns/<campaign_slug>/content/assets/missing.png` | `dm` | `404 text/html` generic page | `404 application/json` | `content_asset_not_found` |
| `GET` | `/api/v1/campaigns/<campaign_slug>/content/characters/missing-character` | `dm` | `404 text/html` generic page | `404 application/json` | `content_character_not_found` |
| `GET` | `/campaigns/<campaign_slug>/assets/missing.png` | `dm` | `404 text/html` generic page | `404 application/json` | `campaign_asset_not_found` |

This is an explicit compatibility boundary for the TypeScript rewrite evidence,
not a Flask production behavior change. Cutover still needs an API-version or
client-compatibility decision before treating JSON-normalized missing publishing
resources as a general contract across all route families.

## Source-Level 404 Notes

- `player_wiki/api.py` defines the JSON error envelope in `json_error` near
  `player_wiki/api.py:264`.
- The API middleware and handlers use many `abort(404)` branches. These fall
  through to the Flask app 404 handler at `player_wiki/app.py:9205`, which renders
  `not_found.html` and returns `text/html`.
- The explicit JSON `404 not_found` case observed in source is character controls
  deletion when the route-target character disappears during delete
  (`player_wiki/api.py:9037`).
- Several mutation routes report missing row-like resources as JSON `400
  validation_error` instead of `404`, including staged session article update, DM
  Content statblock update, DM Content condition update, and combatant delete.
