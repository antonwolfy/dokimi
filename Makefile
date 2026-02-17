.PHONY: validate-benchmark-spec

validate-benchmark-spec:
	@command -v yq >/dev/null 2>&1 || { echo "ERROR: yq is not installed"; exit 1; }
	@command -v npx >/dev/null 2>&1 || { echo "ERROR: npx is not installed"; exit 1; }
	@echo "Checking YAML parse for benchmarks/spec.v1.yaml"
	@yq eval '.' benchmarks/spec.v1.yaml >/dev/null
	@echo "Converting YAML -> JSON and validating against benchmarks/spec.schema.json"
	@yq eval -o=json benchmarks/spec.v1.yaml | npx --yes ajv-cli validate -s benchmarks/spec.schema.json -d /dev/stdin --spec=draft2020
	@echo "✅ Benchmark spec is valid"
