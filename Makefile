.PHONY: validate-benchmark-spec

validate-benchmark-spec:
	@command -v yq >/dev/null 2>&1 || { echo "ERROR: yq is not installed"; exit 1; }
	@echo "Checking YAML parse for benchmarks/spec.v1.yaml"
	@yq eval '.' benchmarks/spec.v1.yaml >/dev/null
	@echo "Converting YAML -> JSON and validating against benchmarks/spec.schema.json"
	@yq eval -o=json benchmarks/spec.v1.yaml > benchmarks/.spec.v1.tmp.json
	@if command -v ajv >/dev/null 2>&1; then \
		ajv validate -s benchmarks/spec.schema.json -d benchmarks/.spec.v1.tmp.json --spec=draft2020; \
	elif command -v npx >/dev/null 2>&1; then \
		mkdir -p .npm-cache; \
		npm_config_cache=$(PWD)/.npm-cache npx --yes ajv-cli validate -s benchmarks/spec.schema.json -d benchmarks/.spec.v1.tmp.json --spec=draft2020; \
	else \
		echo "ERROR: neither 'ajv' nor 'npx' is installed"; \
		echo "Install one of:"; \
		echo "  npm i -g ajv-cli"; \
		echo "  # or install Node.js/npm to use npx"; \
		exit 1; \
	fi
	@rm -f benchmarks/.spec.v1.tmp.json
	@echo "✅ Benchmark spec is valid"
