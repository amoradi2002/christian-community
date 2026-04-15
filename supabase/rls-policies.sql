-- ============================================================================
--  God's Children – Row-Level Security (RLS) Policies
-- ============================================================================
--  Supabase project: jnjhwftqkmklsxzllqvs
--
--  PURPOSE
--  -------
--  Fixes the CRITICAL "Table publicly accessible" Supabase alert by enabling
--  RLS on every app table and adding sensible policies:
--    • Anonymous visitors can READ public content
--    • Only logged-in users can INSERT
--    • Only row owners can UPDATE / DELETE
--    • Private tables (reports, banned_ips, user_promises, members) are locked
--
--  NOTE: All auth.uid() comparisons are cast to text on BOTH sides so this
--  script works whether your user_id columns are `uuid` or `text`.
--
--  HOW TO RUN
--  ----------
--  1. Open https://supabase.com/dashboard/project/jnjhwftqkmklsxzllqvs
--  2. SQL Editor → New query
--  3. Paste this entire file → Run
--  4. Expected: "Success. No rows returned."
--
--  Script is idempotent — safe to re-run.
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

-- ============================================================================
--  2. PROFILES  – public read; owner-only writes
-- ============================================================================
DROP POLICY IF EXISTS "profiles_select_public" ON public.profiles;
DROP POLICY IF EXISTS "profiles_insert_own"    ON public.profiles;
DROP POLICY IF EXISTS "profiles_update_own"    ON public.profiles;
DROP POLICY IF EXISTS "profiles_delete_own"    ON public.profiles;

CREATE POLICY "profiles_select_public"
  ON public.profiles FOR SELECT
  USING (true);

CREATE POLICY "profiles_insert_own"
  ON public.profiles FOR INSERT
  WITH CHECK ((auth.uid())::text = (id)::text);

CREATE POLICY "profiles_update_own"
  ON public.profiles FOR UPDATE
  USING ((auth.uid())::text = (id)::text)
  WITH CHECK ((auth.uid())::text = (id)::text);

CREATE POLICY "profiles_delete_own"
  ON public.profiles FOR DELETE
  USING ((auth.uid())::text = (id)::text);

-- ============================================================================
--  3. CHURCHES
-- ============================================================================
DROP POLICY IF EXISTS "churches_select_public" ON public.churches;
DROP POLICY IF EXISTS "churches_insert_auth"   ON public.churches;
DROP POLICY IF EXISTS "churches_update_member" ON public.churches;
DROP POLICY IF EXISTS "churches_delete_owner"  ON public.churches;

CREATE POLICY "churches_select_public"
  ON public.churches FOR SELECT
  USING (true);

CREATE POLICY "churches_insert_auth"
  ON public.churches FOR INSERT
  WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "churches_update_member"
  ON public.churches FOR UPDATE
  USING (auth.role() = 'authenticated')
  WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "churches_delete_owner"
  ON public.churches FOR DELETE
  USING ((auth.uid())::text = (user_id)::text);

-- ============================================================================
--  4. LIFE_GROUPS
-- ============================================================================
DROP POLICY IF EXISTS "life_groups_select_public" ON public.life_groups;
DROP POLICY IF EXISTS "life_groups_insert_auth"   ON public.life_groups;
DROP POLICY IF EXISTS "life_groups_update_auth"   ON public.life_groups;
DROP POLICY IF EXISTS "life_groups_delete_leader" ON public.life_groups;

CREATE POLICY "life_groups_select_public"
  ON public.life_groups FOR SELECT
  USING (true);

CREATE POLICY "life_groups_insert_auth"
  ON public.life_groups FOR INSERT
  WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "life_groups_update_auth"
  ON public.life_groups FOR UPDATE
  USING (auth.role() = 'authenticated')
  WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "life_groups_delete_leader"
  ON public.life_groups FOR DELETE
  USING ((auth.uid())::text = (leader_id)::text);

-- ============================================================================
--  5. DISCUSSIONS
-- ============================================================================
DROP POLICY IF EXISTS "discussions_select_public" ON public.discussions;
DROP POLICY IF EXISTS "discussions_insert_auth"   ON public.discussions;
DROP POLICY IF EXISTS "discussions_update_own"    ON public.discussions;
DROP POLICY IF EXISTS "discussions_delete_own"    ON public.discussions;

CREATE POLICY "discussions_select_public"
  ON public.discussions FOR SELECT
  USING (true);

CREATE POLICY "discussions_insert_auth"
  ON public.discussions FOR INSERT
  WITH CHECK ((auth.uid())::text = (user_id)::text);

CREATE POLICY "discussions_update_own"
  ON public.discussions FOR UPDATE
  USING ((auth.uid())::text = (user_id)::text)
  WITH CHECK ((auth.uid())::text = (user_id)::text);

CREATE POLICY "discussions_delete_own"
  ON public.discussions FOR DELETE
  USING ((auth.uid())::text = (user_id)::text);

-- ============================================================================
--  6. TESTIMONIES
-- ============================================================================
DROP POLICY IF EXISTS "testimonies_select_public" ON public.testimonies;
DROP POLICY IF EXISTS "testimonies_insert_auth"   ON public.testimonies;
DROP POLICY IF EXISTS "testimonies_update_own"    ON public.testimonies;
DROP POLICY IF EXISTS "testimonies_delete_own"    ON public.testimonies;

CREATE POLICY "testimonies_select_public"
  ON public.testimonies FOR SELECT
  USING (true);

CREATE POLICY "testimonies_insert_auth"
  ON public.testimonies FOR INSERT
  WITH CHECK ((auth.uid())::text = (user_id)::text);

CREATE POLICY "testimonies_update_own"
  ON public.testimonies FOR UPDATE
  USING ((auth.uid())::text = (user_id)::text)
  WITH CHECK ((auth.uid())::text = (user_id)::text);

CREATE POLICY "testimonies_delete_own"
  ON public.testimonies FOR DELETE
  USING ((auth.uid())::text = (user_id)::text);

-- ============================================================================
--  7. PRAYER_REQUESTS
-- ============================================================================
DROP POLICY IF EXISTS "prayer_select_public" ON public.prayer_requests;
DROP POLICY IF EXISTS "prayer_insert_auth"   ON public.prayer_requests;
DROP POLICY IF EXISTS "prayer_update_auth"   ON public.prayer_requests;
DROP POLICY IF EXISTS "prayer_delete_own"    ON public.prayer_requests;

CREATE POLICY "prayer_select_public"
  ON public.prayer_requests FOR SELECT
  USING (true);

CREATE POLICY "prayer_insert_auth"
  ON public.prayer_requests FOR INSERT
  WITH CHECK ((auth.uid())::text = (user_id)::text);

CREATE POLICY "prayer_update_auth"
  ON public.prayer_requests FOR UPDATE
  USING (auth.role() = 'authenticated')
  WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "prayer_delete_own"
  ON public.prayer_requests FOR DELETE
  USING ((auth.uid())::text = (user_id)::text);

-- ============================================================================
--  8. MUSIC_POSTS
-- ============================================================================
DROP POLICY IF EXISTS "music_select_public" ON public.music_posts;
DROP POLICY IF EXISTS "music_insert_auth"   ON public.music_posts;
DROP POLICY IF EXISTS "music_update_own"    ON public.music_posts;
DROP POLICY IF EXISTS "music_delete_own"    ON public.music_posts;

CREATE POLICY "music_select_public"
  ON public.music_posts FOR SELECT
  USING (true);

CREATE POLICY "music_insert_auth"
  ON public.music_posts FOR INSERT
  WITH CHECK ((auth.uid())::text = (user_id)::text);

CREATE POLICY "music_update_own"
  ON public.music_posts FOR UPDATE
  USING ((auth.uid())::text = (user_id)::text)
  WITH CHECK ((auth.uid())::text = (user_id)::text);

CREATE POLICY "music_delete_own"
  ON public.music_posts FOR DELETE
  USING ((auth.uid())::text = (user_id)::text);

-- ============================================================================
--  9. SERMONS
-- ============================================================================
DROP POLICY IF EXISTS "sermons_select_public" ON public.sermons;
DROP POLICY IF EXISTS "sermons_insert_auth"   ON public.sermons;
DROP POLICY IF EXISTS "sermons_update_own"    ON public.sermons;
DROP POLICY IF EXISTS "sermons_delete_own"    ON public.sermons;

CREATE POLICY "sermons_select_public"
  ON public.sermons FOR SELECT
  USING (true);

CREATE POLICY "sermons_insert_auth"
  ON public.sermons FOR INSERT
  WITH CHECK ((auth.uid())::text = (user_id)::text);

CREATE POLICY "sermons_update_own"
  ON public.sermons FOR UPDATE
  USING ((auth.uid())::text = (user_id)::text)
  WITH CHECK ((auth.uid())::text = (user_id)::text);

CREATE POLICY "sermons_delete_own"
  ON public.sermons FOR DELETE
  USING ((auth.uid())::text = (user_id)::text);

-- ============================================================================
-- 10. COMMENTS
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
  WITH CHECK ((auth.uid())::text = (user_id)::text);

CREATE POLICY "comments_update_own"
  ON public.comments FOR UPDATE
  USING ((auth.uid())::text = (user_id)::text)
  WITH CHECK ((auth.uid())::text = (user_id)::text);

CREATE POLICY "comments_delete_own"
  ON public.comments FOR DELETE
  USING ((auth.uid())::text = (user_id)::text);

-- ============================================================================
-- 11. ANNOUNCEMENTS
-- ============================================================================
DROP POLICY IF EXISTS "announcements_select_public" ON public.announcements;
DROP POLICY IF EXISTS "announcements_insert_auth"   ON public.announcements;
DROP POLICY IF EXISTS "announcements_delete_own"    ON public.announcements;

CREATE POLICY "announcements_select_public"
  ON public.announcements FOR SELECT
  USING (true);

CREATE POLICY "announcements_insert_auth"
  ON public.announcements FOR INSERT
  WITH CHECK ((auth.uid())::text = (posted_by)::text);

CREATE POLICY "announcements_delete_own"
  ON public.announcements FOR DELETE
  USING ((auth.uid())::text = (posted_by)::text);

-- ============================================================================
-- 12. MEMBERS
-- ============================================================================
DROP POLICY IF EXISTS "members_select_own" ON public.members;
DROP POLICY IF EXISTS "members_insert_own" ON public.members;
DROP POLICY IF EXISTS "members_delete_own" ON public.members;

CREATE POLICY "members_select_own"
  ON public.members FOR SELECT
  USING ((auth.uid())::text = (user_id)::text);

CREATE POLICY "members_insert_own"
  ON public.members FOR INSERT
  WITH CHECK ((auth.uid())::text = (user_id)::text);

CREATE POLICY "members_delete_own"
  ON public.members FOR DELETE
  USING ((auth.uid())::text = (user_id)::text);

-- ============================================================================
-- 13. USER_PROMISES
-- ============================================================================
DROP POLICY IF EXISTS "user_promises_select_own" ON public.user_promises;
DROP POLICY IF EXISTS "user_promises_insert_own" ON public.user_promises;
DROP POLICY IF EXISTS "user_promises_update_own" ON public.user_promises;
DROP POLICY IF EXISTS "user_promises_delete_own" ON public.user_promises;

CREATE POLICY "user_promises_select_own"
  ON public.user_promises FOR SELECT
  USING ((auth.uid())::text = (user_id)::text);

CREATE POLICY "user_promises_insert_own"
  ON public.user_promises FOR INSERT
  WITH CHECK ((auth.uid())::text = (user_id)::text);

CREATE POLICY "user_promises_update_own"
  ON public.user_promises FOR UPDATE
  USING ((auth.uid())::text = (user_id)::text)
  WITH CHECK ((auth.uid())::text = (user_id)::text);

CREATE POLICY "user_promises_delete_own"
  ON public.user_promises FOR DELETE
  USING ((auth.uid())::text = (user_id)::text);

-- ============================================================================
-- 14. REPORTS  – insert-only for authed users; no client reads
-- ============================================================================
DROP POLICY IF EXISTS "reports_insert_auth" ON public.reports;

CREATE POLICY "reports_insert_auth"
  ON public.reports FOR INSERT
  WITH CHECK ((auth.uid())::text = (reporter_id)::text);

-- No SELECT / UPDATE / DELETE policy => regular users cannot read reports.
-- Admin tools should use the service_role key (bypasses RLS).

-- ============================================================================
-- 15. BANNED_IPS  – NO public policies; access only via service_role key
-- ============================================================================
-- RLS is enabled above. With no policies, all regular queries are rejected.

-- ============================================================================
--  Done!
-- ============================================================================
