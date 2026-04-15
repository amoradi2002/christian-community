-- ============================================================================
--  God's Children – Row-Level Security (RLS) Policies
-- ============================================================================
--  Supabase project: jnjhwftqkmklsxzllqvs
--
--  PURPOSE
--  -------
--  This script fixes the CRITICAL "Table publicly accessible" security alert
--  by enabling RLS on every table the app uses and adding sensible policies.
--
--  WITHOUT these policies, ANYONE with the project URL could read, edit, or
--  delete ANY row in ANY table. With them:
--    • Anonymous visitors can READ public content (churches, posts, etc.)
--    • Only logged-in users can INSERT new rows
--    • Only the owner of a row can UPDATE / DELETE it
--    • Private tables (reports, banned_ips, user_promises, members) are
--      locked down to the owner / service role only.
--
--  HOW TO RUN
--  ----------
--  1. Open https://supabase.com/dashboard/project/jnjhwftqkmklsxzllqvs
--  2. Click "SQL Editor" → "New query"
--  3. Paste this ENTIRE file and click "Run"
--  4. You should see "Success. No rows returned."
--  5. In the Supabase "Advisors" or "Database → Linter" page, the
--     rls_disabled_in_public alert should clear within a minute.
--
--  This script is idempotent — safe to re-run.
-- ============================================================================

-- ----------------------------------------------------------------------------
--  1. Enable RLS on every table
-- ----------------------------------------------------------------------------
ALTER TABLE IF EXISTS public.profiles          ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.churches          ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.life_groups       ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.discussions       ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.testimonies       ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.prayer_requests   ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.music_posts       ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.sermons           ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.comments          ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.announcements     ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.members           ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.user_promises     ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.reports           ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.banned_ips        ENABLE ROW LEVEL SECURITY;

-- ----------------------------------------------------------------------------
--  Helper: drop-then-recreate pattern so the script is re-runnable.
--  Each policy is dropped first (if exists) then recreated.
-- ----------------------------------------------------------------------------

-- ============================================================================
--  2. PROFILES  – public read (display names on posts); owner-only writes
-- ============================================================================
DROP POLICY IF EXISTS "profiles_select_public"     ON public.profiles;
DROP POLICY IF EXISTS "profiles_insert_own"        ON public.profiles;
DROP POLICY IF EXISTS "profiles_update_own"        ON public.profiles;
DROP POLICY IF EXISTS "profiles_delete_own"        ON public.profiles;

CREATE POLICY "profiles_select_public"
  ON public.profiles FOR SELECT
  USING (true);

CREATE POLICY "profiles_insert_own"
  ON public.profiles FOR INSERT
  WITH CHECK (auth.uid() = id);

CREATE POLICY "profiles_update_own"
  ON public.profiles FOR UPDATE
  USING (auth.uid() = id)
  WITH CHECK (auth.uid() = id);

CREATE POLICY "profiles_delete_own"
  ON public.profiles FOR DELETE
  USING (auth.uid() = id);

-- ============================================================================
--  3. CHURCHES  – public read; authenticated insert; owner update/delete
-- ============================================================================
DROP POLICY IF EXISTS "churches_select_public"   ON public.churches;
DROP POLICY IF EXISTS "churches_insert_auth"     ON public.churches;
DROP POLICY IF EXISTS "churches_update_member"   ON public.churches;
DROP POLICY IF EXISTS "churches_delete_owner"    ON public.churches;

CREATE POLICY "churches_select_public"
  ON public.churches FOR SELECT
  USING (true);

CREATE POLICY "churches_insert_auth"
  ON public.churches FOR INSERT
  WITH CHECK (auth.role() = 'authenticated');

-- Any authenticated user can UPDATE (needed for member_count on join).
-- NOTE: To fully lock this down, move member_count updates into a
-- SECURITY DEFINER RPC and change this policy to owner-only.
CREATE POLICY "churches_update_member"
  ON public.churches FOR UPDATE
  USING (auth.role() = 'authenticated')
  WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "churches_delete_owner"
  ON public.churches FOR DELETE
  USING (auth.uid() = user_id);

-- ============================================================================
--  4. LIFE_GROUPS  – public read; authenticated insert; owner delete
-- ============================================================================
DROP POLICY IF EXISTS "life_groups_select_public"   ON public.life_groups;
DROP POLICY IF EXISTS "life_groups_insert_auth"     ON public.life_groups;
DROP POLICY IF EXISTS "life_groups_update_auth"     ON public.life_groups;
DROP POLICY IF EXISTS "life_groups_delete_leader"   ON public.life_groups;

CREATE POLICY "life_groups_select_public"
  ON public.life_groups FOR SELECT
  USING (true);

CREATE POLICY "life_groups_insert_auth"
  ON public.life_groups FOR INSERT
  WITH CHECK (auth.role() = 'authenticated');

-- Same member_count caveat as churches above.
CREATE POLICY "life_groups_update_auth"
  ON public.life_groups FOR UPDATE
  USING (auth.role() = 'authenticated')
  WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "life_groups_delete_leader"
  ON public.life_groups FOR DELETE
  USING (auth.uid() = leader_id);

-- ============================================================================
--  5. DISCUSSIONS (Bible comments)
-- ============================================================================
DROP POLICY IF EXISTS "discussions_select_public"  ON public.discussions;
DROP POLICY IF EXISTS "discussions_insert_auth"    ON public.discussions;
DROP POLICY IF EXISTS "discussions_update_own"     ON public.discussions;
DROP POLICY IF EXISTS "discussions_delete_own"     ON public.discussions;

CREATE POLICY "discussions_select_public"
  ON public.discussions FOR SELECT
  USING (true);

CREATE POLICY "discussions_insert_auth"
  ON public.discussions FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "discussions_update_own"
  ON public.discussions FOR UPDATE
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "discussions_delete_own"
  ON public.discussions FOR DELETE
  USING (auth.uid() = user_id);

-- ============================================================================
--  6. TESTIMONIES
-- ============================================================================
DROP POLICY IF EXISTS "testimonies_select_public"  ON public.testimonies;
DROP POLICY IF EXISTS "testimonies_insert_auth"    ON public.testimonies;
DROP POLICY IF EXISTS "testimonies_update_own"     ON public.testimonies;
DROP POLICY IF EXISTS "testimonies_delete_own"     ON public.testimonies;

CREATE POLICY "testimonies_select_public"
  ON public.testimonies FOR SELECT
  USING (true);

CREATE POLICY "testimonies_insert_auth"
  ON public.testimonies FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "testimonies_update_own"
  ON public.testimonies FOR UPDATE
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "testimonies_delete_own"
  ON public.testimonies FOR DELETE
  USING (auth.uid() = user_id);

-- ============================================================================
--  7. PRAYER_REQUESTS  – pray_count needs UPDATE by any authed user
-- ============================================================================
DROP POLICY IF EXISTS "prayer_select_public"      ON public.prayer_requests;
DROP POLICY IF EXISTS "prayer_insert_auth"        ON public.prayer_requests;
DROP POLICY IF EXISTS "prayer_update_auth"        ON public.prayer_requests;
DROP POLICY IF EXISTS "prayer_delete_own"         ON public.prayer_requests;

CREATE POLICY "prayer_select_public"
  ON public.prayer_requests FOR SELECT
  USING (true);

CREATE POLICY "prayer_insert_auth"
  ON public.prayer_requests FOR INSERT
  WITH CHECK (auth.uid() = user_id);

-- UPDATE open to authenticated users so the 🙏 "Praying" button works.
-- To harden: replace this with an RPC that only increments pray_count.
CREATE POLICY "prayer_update_auth"
  ON public.prayer_requests FOR UPDATE
  USING (auth.role() = 'authenticated')
  WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "prayer_delete_own"
  ON public.prayer_requests FOR DELETE
  USING (auth.uid() = user_id);

-- ============================================================================
--  8. MUSIC_POSTS
-- ============================================================================
DROP POLICY IF EXISTS "music_select_public"   ON public.music_posts;
DROP POLICY IF EXISTS "music_insert_auth"     ON public.music_posts;
DROP POLICY IF EXISTS "music_update_own"      ON public.music_posts;
DROP POLICY IF EXISTS "music_delete_own"      ON public.music_posts;

CREATE POLICY "music_select_public"
  ON public.music_posts FOR SELECT
  USING (true);

CREATE POLICY "music_insert_auth"
  ON public.music_posts FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "music_update_own"
  ON public.music_posts FOR UPDATE
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "music_delete_own"
  ON public.music_posts FOR DELETE
  USING (auth.uid() = user_id);

-- ============================================================================
--  9. SERMONS
-- ============================================================================
DROP POLICY IF EXISTS "sermons_select_public"  ON public.sermons;
DROP POLICY IF EXISTS "sermons_insert_auth"    ON public.sermons;
DROP POLICY IF EXISTS "sermons_update_own"     ON public.sermons;
DROP POLICY IF EXISTS "sermons_delete_own"     ON public.sermons;

CREATE POLICY "sermons_select_public"
  ON public.sermons FOR SELECT
  USING (true);

CREATE POLICY "sermons_insert_auth"
  ON public.sermons FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "sermons_update_own"
  ON public.sermons FOR UPDATE
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "sermons_delete_own"
  ON public.sermons FOR DELETE
  USING (auth.uid() = user_id);

-- ============================================================================
-- 10. COMMENTS (encouragements on prayer requests)
-- ============================================================================
DROP POLICY IF EXISTS "comments_select_public" ON public.comments;
DROP POLICY IF EXISTS "comments_insert_auth"   ON public.comments;
DROP POLICY IF EXISTS "comments_update_own"    ON public.comments;
DROP POLICY IF EXISTS "comments_delete_own"    ON public.comments;

CREATE POLICY "comments_select_public"
  ON public.comments FOR SELECT
  USING (true);

CREATE POLICY "comments_insert_auth"
  ON public.comments FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "comments_update_own"
  ON public.comments FOR UPDATE
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "comments_delete_own"
  ON public.comments FOR DELETE
  USING (auth.uid() = user_id);

-- ============================================================================
-- 11. ANNOUNCEMENTS  (posted by church/group leaders)
-- ============================================================================
DROP POLICY IF EXISTS "announcements_select_public"  ON public.announcements;
DROP POLICY IF EXISTS "announcements_insert_auth"    ON public.announcements;
DROP POLICY IF EXISTS "announcements_delete_own"     ON public.announcements;

CREATE POLICY "announcements_select_public"
  ON public.announcements FOR SELECT
  USING (true);

CREATE POLICY "announcements_insert_auth"
  ON public.announcements FOR INSERT
  WITH CHECK (auth.uid() = posted_by);

CREATE POLICY "announcements_delete_own"
  ON public.announcements FOR DELETE
  USING (auth.uid() = posted_by);

-- ============================================================================
-- 12. MEMBERS  – private; each user sees / manages only their own rows
-- ============================================================================
DROP POLICY IF EXISTS "members_select_own"   ON public.members;
DROP POLICY IF EXISTS "members_insert_own"   ON public.members;
DROP POLICY IF EXISTS "members_delete_own"   ON public.members;

CREATE POLICY "members_select_own"
  ON public.members FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "members_insert_own"
  ON public.members FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "members_delete_own"
  ON public.members FOR DELETE
  USING (auth.uid() = user_id);

-- ============================================================================
-- 13. USER_PROMISES  – fully private per user
-- ============================================================================
DROP POLICY IF EXISTS "user_promises_select_own"   ON public.user_promises;
DROP POLICY IF EXISTS "user_promises_insert_own"   ON public.user_promises;
DROP POLICY IF EXISTS "user_promises_update_own"   ON public.user_promises;
DROP POLICY IF EXISTS "user_promises_delete_own"   ON public.user_promises;

CREATE POLICY "user_promises_select_own"
  ON public.user_promises FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "user_promises_insert_own"
  ON public.user_promises FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "user_promises_update_own"
  ON public.user_promises FOR UPDATE
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "user_promises_delete_own"
  ON public.user_promises FOR DELETE
  USING (auth.uid() = user_id);

-- ============================================================================
-- 14. REPORTS  – insert-only for authed users; reads restricted to admins
-- ============================================================================
DROP POLICY IF EXISTS "reports_insert_auth"   ON public.reports;
DROP POLICY IF EXISTS "reports_select_none"   ON public.reports;

CREATE POLICY "reports_insert_auth"
  ON public.reports FOR INSERT
  WITH CHECK (auth.uid() = reporter_id);

-- No SELECT / UPDATE / DELETE policy => regular users cannot read reports.
-- Admin dashboards should use the service_role key which bypasses RLS.

-- ============================================================================
-- 15. BANNED_IPS  – NO public policies; access only via service_role key
-- ============================================================================
-- RLS is enabled above. By not creating any policies, every regular query
-- will be rejected. Your moderation code that checks banned IPs should run
-- with the service_role key (server-side only), or move that check into a
-- SECURITY DEFINER function.

-- ============================================================================
--  Done!
-- ============================================================================
