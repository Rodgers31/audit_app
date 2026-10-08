# Production Deployment Checklist

## Pre-Deployment

### Security

- [ ] Generate new SECRET_KEY and store in secrets manager
- [ ] Configure CORS with actual domain whitelist
- [ ] Set up SSL/TLS certificates (Let's Encrypt or ACM)
- [ ] Enable rate limiting on all endpoints
- [ ] Configure Sentry error tracking
- [ ] Review and restrict admin API access
- [ ] Enable audit logging
- [ ] Scan for security vulnerabilities (npm audit, pip audit)

### Database

- [ ] Set up managed PostgreSQL (RDS, Supabase, etc.)
- [ ] Configure automated daily backups
- [ ] Run database migrations (`alembic upgrade head`)
- [ ] Add performance indexes
- [ ] Configure connection pooling (pgbouncer if needed)
- [ ] Test database restore procedure

### Caching

- [ ] Set up managed Redis (ElastiCache, Upstash, etc.)
- [ ] Configure cache TTL values
- [ ] Test cache invalidation

### Environment Variables

- [ ] Copy `.env.production.example` to `.env`
- [ ] Fill in all production values
- [ ] Store secrets in AWS Secrets Manager / HashiCorp Vault
- [ ] Configure environment variables in deployment platform

### Monitoring

- [ ] Configure Sentry DSN
- [ ] Set up Prometheus metrics collection
- [ ] Create Grafana dashboards
- [ ] Configure log aggregation (CloudWatch, ELK, Datadog)
- [ ] Set up uptime monitoring (UptimeRobot, Pingdom)
- [ ] Configure alerting (PagerDuty, Opsgenie, Slack)

### Testing

- [ ] Run all test suites (`pytest`, `npm test`)
- [ ] Perform load testing (target: 1000 req/sec)
- [ ] Test ETL pipeline end-to-end
- [ ] Verify data accuracy with sample data
- [ ] Test backup and restore procedures

### Legal & Compliance

- [ ] Register with Kenya Data Protection Commissioner
- [ ] Add privacy policy to website
- [ ] Add terms of service to website
- [ ] Add prominent disclaimer on all pages
- [ ] Set up data correction request workflow
- [ ] Get legal review (recommended)

## Deployment Steps

### 1. Build Images

```bash
# Backend
docker build -f backend/Dockerfile.prod -t audit-app-backend:latest ./backend

# Frontend: export the intended deployment's public values before building.
docker build -f frontend/Dockerfile.prod -t audit-app-frontend:latest \
  --build-arg NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:?Set the public backend URL}" \
  --build-arg NEXT_PUBLIC_SUPABASE_URL="${NEXT_PUBLIC_SUPABASE_URL:?Set the public Supabase URL}" \
  --build-arg NEXT_PUBLIC_SUPABASE_ANON_KEY="${NEXT_PUBLIC_SUPABASE_ANON_KEY:?Set the public anon key}" \
  ./frontend
```

The frontend embeds these public values at build time. Use an image built for
the destination environment; runtime public overrides must match its build
configuration. `INTERNAL_API_URL` is an optional server-only address for SSR
requests, such as `http://backend:8000` on the Compose network. It does not change
the browser's public API URL. See the [configuration verification](verification/2026-10-08-pr516-configuration.md).

### 2. Push to Registry

```bash
# AWS ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com
docker tag audit-app-backend:latest <account>.dkr.ecr.us-east-1.amazonaws.com/audit-app-backend:latest
docker push <account>.dkr.ecr.us-east-1.amazonaws.com/audit-app-backend:latest
```

### 3. Deploy Services

```bash
# Using docker-compose (staging/small deployments)
docker-compose -f docker-compose.prod.yml up -d

# Or use managed services:
# - Frontend: Vercel, Netlify
# - Backend: Railway, Render, AWS ECS, GCP Cloud Run
# - Database: AWS RDS, Supabase
```

### 4. Run Database Migrations

```bash
docker exec -it backend alembic upgrade head
```

### 5. Seed Initial Data (if needed)

```bash
docker exec -it backend python -m etl.seed_minimums
```

### 6. Verify Deployment

- [ ] Check `/health` endpoint returns 200
- [ ] Check `/health/detailed` shows all components healthy
- [ ] Verify frontend loads correctly
- [ ] Test critical user flows
- [ ] Check error tracking (Sentry) receiving events
- [ ] Verify metrics endpoint `/metrics` working
- [ ] Test rate limiting

## Post-Deployment

### Monitoring Setup

- [ ] Create performance dashboard (Grafana)
- [ ] Set up error alerts (Sentry → Slack)
- [ ] Configure uptime alerts (UptimeRobot → Email)
- [ ] Set up log monitoring queries
- [ ] Create weekly reports

### Performance Optimization

- [ ] Monitor response times (target: p95 < 200ms)
- [ ] Check database query performance
- [ ] Verify cache hit rates
- [ ] Monitor ETL job success rates

### Documentation

- [ ] Update README with deployment info
- [ ] Create runbook for common incidents
- [ ] Document rollback procedures
- [ ] Create on-call rotation schedule (if applicable)

## Rollback Plan

If issues are detected:

1. **Immediate Rollback**:

   ```bash
   # Revert to previous deployment
   kubectl rollout undo deployment/audit-app-backend
   # Or
   docker-compose down && docker-compose -f docker-compose.previous.yml up -d
   ```

2. **Database Rollback** (if migrations were run):

   ```bash
   alembic downgrade -1
   ```

3. **Notify Users**:
   - Post status update
   - Send email notification (if applicable)

## Maintenance Windows

Schedule regular maintenance for:

- Database updates: Monthly, Sunday 2-4 AM EAT
- Security patches: As needed
- ETL pipeline updates: Weekly, Saturday 11 PM EAT

## Success Metrics

Monitor these KPIs post-deployment:

- API uptime: Target 99.9%
- Response time p95: Target < 200ms
- Error rate: Target < 0.1%
- ETL success rate: Target > 95%
- User satisfaction: Monitor feedback

## Emergency Contacts

- DevOps Lead: [Contact]
- Database Admin: [Contact]
- Security Lead: [Contact]
- Legal Counsel: [Contact]

## Incident Response

1. **Detect**: Automated alerts or user reports
2. **Assess**: Check monitoring dashboards
3. **Respond**: Follow runbook procedures
4. **Communicate**: Update status page
5. **Resolve**: Apply fix or rollback
6. **Document**: Create post-mortem report

---

**Last Updated**: October 1, 2025
**Version**: 1.0
