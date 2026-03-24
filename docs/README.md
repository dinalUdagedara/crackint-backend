# Crackint Backend Documentation

Welcome to the Crackint Backend API documentation. This folder contains technical documentation for developers.

## 📚 Available Documentation

### For Frontend Developers

| Document | Description | Use Case |
|----------|-------------|----------|
| [**ADMIN_AND_USER_PROFILE.md**](./ADMIN_AND_USER_PROFILE.md) | Admin API, `PATCH /auth/me`, profile images (S3) | Admin dashboard & account settings |
| [**QUICK_REFERENCE.md**](./QUICK_REFERENCE.md) | Quick reference guide for job entity validation | Quick lookup, code snippets |
| [**frontend-job-entity-validation.md**](./frontend-job-entity-validation.md) | Complete guide for job entity AI validation feature | Integration guide, detailed examples |

### For All Developers

| Document | Description | Use Case |
|----------|-------------|----------|
| [**CHANGELOG.md**](./CHANGELOG.md) | API changes and version history | Track changes, migration guides |

## 🚀 Quick Start

### Frontend Integration

If you're integrating the job entity extraction feature:

1. **Start here**: [QUICK_REFERENCE.md](./QUICK_REFERENCE.md) - Get code snippets
2. **Full details**: [frontend-job-entity-validation.md](./frontend-job-entity-validation.md) - Complete integration guide
3. **Updates**: [CHANGELOG.md](./CHANGELOG.md) - See what's new

### Key Features

#### Job Entity Extraction with AI Validation
- Extract entities from job descriptions (PDF or text)
- Optional AI validation for improved accuracy
- Backward compatible with existing integrations

**Quick example**:
```javascript
// Add ?validate=true for AI-enhanced extraction
POST /api/v1/jobs/extract?validate=true
```

See [QUICK_REFERENCE.md](./QUICK_REFERENCE.md) for more examples.

## 🔍 What's New

### Latest Updates (Feb 11, 2026)
- ✨ **New**: AI-powered validation for job entity extraction
- 📝 Added `validate` query parameter to `/api/v1/jobs/extract`
- 🎯 15-30% accuracy improvement when validation is enabled
- ✅ Fully backward compatible

See [CHANGELOG.md](./CHANGELOG.md) for complete details.

## 📖 Documentation Index

### API Endpoints

#### Job Entity Extraction
- **Endpoint**: `POST /api/v1/jobs/extract`
- **Documentation**: [frontend-job-entity-validation.md](./frontend-job-entity-validation.md)
- **Quick Reference**: [QUICK_REFERENCE.md](./QUICK_REFERENCE.md)

#### Resume Entity Extraction
- **Endpoint**: `POST /api/v1/resume/extract`
- **Features**: Similar AI validation available with `validate=true` parameter

## 🛠️ Configuration

### Environment Variables

For AI validation features to work, configure:

```bash
# Job entity validation
JOB_ENTITY_AGENT_ENABLED=true

# Resume entity validation
RESUME_ENTITY_AGENT_ENABLED=true

# Required for both
OPENAI_API_KEY=sk-...
```

## 💡 Tips

- Use AI validation (`validate=true`) for production/important extractions
- Use default mode (`validate=false`) for quick previews or drafts
- AI validation adds 1-3 seconds but improves accuracy significantly

## 🤝 Contributing

When adding new features:

1. Update relevant documentation files
2. Add entry to [CHANGELOG.md](./CHANGELOG.md)
3. Update this README if needed
4. Create frontend documentation for API changes

## 📞 Support

Questions about the documentation or API?

- Check the relevant documentation file first
- Review code examples in [QUICK_REFERENCE.md](./QUICK_REFERENCE.md)
- Contact the backend team for clarification

---

**Last Updated**: February 11, 2026
