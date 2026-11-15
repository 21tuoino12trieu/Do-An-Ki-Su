\set ON_ERROR_STOP on
BEGIN;
CALL knowledge_base.sp_sync_confluence_page(
    '__infra_smoke__', '__page__', 'Title', '<p>one</p>', '/test', 1,
    NULL, 'smoke', now(), 'smoke', now()
);
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM knowledge_base.documents
        WHERE bot_id = '__infra_smoke__' AND page_id = '__page__'
        AND content = '<p>one</p>' AND content_hash = md5('<p>one</p>')) THEN
        RAISE EXCEPTION 'Content/hash insert failed';
    END IF;
END $$;
CALL knowledge_base.sp_sync_confluence_page(
    '__infra_smoke__', '__page__', 'Title revised', '<p>two</p>', '/test', 2,
    NULL, 'smoke', now(), 'smoke', now()
);
DO $$ BEGIN
    IF (SELECT count(*) FROM knowledge_base.documents
        WHERE bot_id = '__infra_smoke__' AND page_id = '__page__') <> 1 THEN
        RAISE EXCEPTION 'Upsert identity failed';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM knowledge_base.documents
        WHERE bot_id = '__infra_smoke__' AND page_id = '__page__'
        AND version_number = 2 AND content_hash = md5('<p>two</p>')) THEN
        RAISE EXCEPTION 'Content/hash update failed';
    END IF;
END $$;
INSERT INTO knowledge_base.sync_jobs (status, started_at)
VALUES ('RUNNING', now());
ROLLBACK;
SELECT 'PASS: procedure, hash, version, unique identity, sync_jobs; test rows rolled back' AS result;
