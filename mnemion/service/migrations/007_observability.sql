-- Numeric diagnostics are separate from immutable evidence and audit records.
-- NULL space denotes a request spanning spaces; only tenant administrators can
-- read those aggregates. Such requests are never counted in an individual space.
CREATE TABLE mnemion.metric_buckets (
    tenant_id uuid NOT NULL REFERENCES mnemion.tenants(id),
    space_id uuid,
    bucket timestamptz NOT NULL,
    stage text NOT NULL CHECK (stage IN ('recall','context','index','purge','librarian','evaluation')),
    mode text NOT NULL CHECK (mode IN ('none','lexical','semantic','hybrid')),
    origin text NOT NULL CHECK (origin IN ('interactive','evaluation','background')),
    generation_id text NOT NULL CHECK (length(generation_id) BETWEEN 1 AND 64),
    calls bigint NOT NULL CHECK (calls>0),
    failures bigint NOT NULL CHECK (failures>=0 AND failures<=calls),
    duration_ms double precision NOT NULL CHECK (duration_ms>=0 AND duration_ms<'Infinity'),
    duration_max_ms double precision NOT NULL CHECK (duration_max_ms>=0 AND duration_max_ms<'Infinity'),
    latency_histogram bigint[] NOT NULL CHECK (cardinality(latency_histogram)=18),
    input_bytes bigint NOT NULL CHECK (input_bytes>=0),
    output_bytes bigint NOT NULL CHECK (output_bytes>=0),
    input_tokens bigint NOT NULL CHECK (input_tokens>=0),
    output_tokens bigint NOT NULL CHECK (output_tokens>=0),
    records bigint NOT NULL CHECK (records>=0),
    chunks bigint NOT NULL CHECK (chunks>=0),
    empty_results bigint NOT NULL CHECK (empty_results>=0),
    fallbacks bigint NOT NULL CHECK (fallbacks>=0),
    incomplete_index bigint NOT NULL CHECK (incomplete_index>=0),
    UNIQUE NULLS NOT DISTINCT (tenant_id,space_id,bucket,stage,mode,origin,generation_id),
    FOREIGN KEY (tenant_id,space_id) REFERENCES mnemion.spaces(tenant_id,id)
);
CREATE INDEX metric_expiry ON mnemion.metric_buckets(bucket);
CREATE INDEX metric_space_time ON mnemion.metric_buckets(tenant_id,space_id,bucket);
ALTER TABLE mnemion.metric_buckets ENABLE ROW LEVEL SECURITY;
CREATE POLICY metric_read ON mnemion.metric_buckets FOR SELECT TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND
      ((space_id IS NOT NULL AND mnemion.authorized(space_id,30))
       OR (space_id IS NULL AND mnemion.administrator())));
CREATE POLICY metric_worker ON mnemion.metric_buckets TO mnemion_worker
    USING (tenant_id=mnemion.tenant()) WITH CHECK (tenant_id=mnemion.tenant());
REVOKE ALL ON mnemion.metric_buckets FROM mnemion_app,mnemion_worker;
GRANT SELECT ON mnemion.metric_buckets TO mnemion_app;
GRANT SELECT,INSERT,UPDATE,DELETE ON mnemion.metric_buckets TO mnemion_worker;

CREATE FUNCTION mnemion.add_histogram(a bigint[], b bigint[]) RETURNS bigint[]
    LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $$
    SELECT ARRAY(SELECT a[i]+b[i] FROM generate_series(1,18) i)
$$;
CREATE AGGREGATE mnemion.sum_histogram(bigint[]) (
    SFUNC=mnemion.add_histogram, STYPE=bigint[],
    INITCOND='{0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0}'
);

-- Readers may record a diagnostic without gaining reviewer access to the
-- complete space's traffic. No text, free-form labels or external URLs accepted.
CREATE FUNCTION mnemion.record_metric(value jsonb) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE row mnemion.metric_buckets;
BEGIN
    row:=jsonb_populate_record(NULL::mnemion.metric_buckets,value);
    IF row.tenant_id IS DISTINCT FROM mnemion.tenant()
       OR (row.space_id IS NOT NULL AND NOT mnemion.authorized(row.space_id))
       OR mnemion.principal() IS NULL
       OR row.bucket>now()+interval '1 minute' OR row.bucket<now()-interval '1 day'
       OR EXISTS(SELECT FROM unnest(row.latency_histogram) h WHERE h<0 OR h IS NULL)
       OR (SELECT sum(h) FROM unnest(row.latency_histogram) h)<>row.calls
    THEN RAISE insufficient_privilege; END IF;
    INSERT INTO mnemion.metric_buckets SELECT row.*
    ON CONFLICT (tenant_id,space_id,bucket,stage,mode,origin,generation_id)
    DO UPDATE SET
      calls=metric_buckets.calls+excluded.calls,
      failures=metric_buckets.failures+excluded.failures,
      duration_ms=metric_buckets.duration_ms+excluded.duration_ms,
      duration_max_ms=greatest(metric_buckets.duration_max_ms,excluded.duration_max_ms),
      latency_histogram=mnemion.add_histogram(metric_buckets.latency_histogram,excluded.latency_histogram),
      input_bytes=metric_buckets.input_bytes+excluded.input_bytes,
      output_bytes=metric_buckets.output_bytes+excluded.output_bytes,
      input_tokens=metric_buckets.input_tokens+excluded.input_tokens,
      output_tokens=metric_buckets.output_tokens+excluded.output_tokens,
      records=metric_buckets.records+excluded.records,
      chunks=metric_buckets.chunks+excluded.chunks,
      empty_results=metric_buckets.empty_results+excluded.empty_results,
      fallbacks=metric_buckets.fallbacks+excluded.fallbacks,
      incomplete_index=metric_buckets.incomplete_index+excluded.incomplete_index;
END
$$;

-- Bounded deletion of expired numeric telemetry; never touches evidence.
CREATE FUNCTION mnemion.expire_metrics() RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE removed integer;
BEGIN
    WITH expired AS (
      SELECT ctid FROM mnemion.metric_buckets WHERE bucket<now()-interval '31 days'
      ORDER BY bucket LIMIT 5000 FOR UPDATE SKIP LOCKED
    ) DELETE FROM mnemion.metric_buckets WHERE ctid IN (SELECT ctid FROM expired);
    GET DIAGNOSTICS removed=ROW_COUNT;
    RETURN removed;
END
$$;
REVOKE ALL ON FUNCTION mnemion.add_histogram(bigint[],bigint[]),
    mnemion.sum_histogram(bigint[]),mnemion.record_metric(jsonb),mnemion.expire_metrics() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.add_histogram(bigint[],bigint[])
    TO mnemion_app,mnemion_worker;
GRANT EXECUTE ON FUNCTION mnemion.sum_histogram(bigint[]) TO mnemion_app,mnemion_worker;
GRANT EXECUTE ON FUNCTION mnemion.record_metric(jsonb) TO mnemion_app;
GRANT EXECUTE ON FUNCTION mnemion.expire_metrics() TO mnemion_app,mnemion_worker;
