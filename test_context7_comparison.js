#!/usr/bin/env node
/**
 * Compare Context7 MCP vs HTTP API
 * 
 * Tests both approaches with sample oneTBB questions and records:
 * - Response quality (content length, specificity)
 * - Latency
 * - Token usage (estimated)
 */

const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
const { StdioClientTransport } = require('@modelcontextprotocol/sdk/client/stdio.js');
const https = require('https');
const { URL } = require('url');

// Sample questions for testing
const TEST_QUESTIONS = [
  "How do I use parallel_for with oneTBB?",
  "How do I integrate oneTBB with CMake?",
  "What are the differences between concurrent_vector and concurrent_queue?"
];

// ---------------------------------------------------------------------------
// HTTP API (current implementation)
// ---------------------------------------------------------------------------

async function fetchViaHTTP(library_id, query, maxTokens = 8000) {
  const url = new URL(`https://context7.com/${library_id}/llms.txt`);
  url.searchParams.append('tokens', maxTokens.toString());
  url.searchParams.append('topic', query);

  return new Promise((resolve, reject) => {
    const startTime = Date.now();
    
    https.get(url.toString(), { headers: { 'User-Agent': 'Context7-Test/1.0' } }, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        const latency = Date.now() - startTime;
        resolve({
          method: 'HTTP API',
          content: data,
          contentLength: data.length,
          latencyMs: latency,
          estimatedTokens: Math.floor(data.length / 4), // rough estimate
          success: res.statusCode === 200
        });
      });
    }).on('error', (err) => {
      reject(err);
    });
  });
}

// ---------------------------------------------------------------------------
// MCP (new approach)
// ---------------------------------------------------------------------------

async function fetchViaMCP(library_id, query) {
  const startTime = Date.now();
  
  try {
    // Create MCP client
    const transport = new StdioClientTransport({
      command: 'npx',
      // Pin version to avoid executing unpinned remote code.
      args: ['-y', '@upstash/context7-mcp@2.1.1']
    });
    
    const client = new Client({
      name: 'context7-test',
      version: '1.0.0'
    }, {
      capabilities: {}
    });
    
    await client.connect(transport);
    
    // List available tools
    const toolsList = await client.listTools();
    
    // Use the query-docs tool
    const result = await client.callTool({
      name: 'query-docs',
      arguments: {
        libraryId: library_id,
        query: query,
        maxTokens: 8000
      }
    });
    
    await client.close();
    
    const latency = Date.now() - startTime;
    const content = JSON.stringify(result.content);
    
    return {
      method: 'MCP',
      content: content,
      contentLength: content.length,
      latencyMs: latency,
      estimatedTokens: Math.floor(content.length / 4),
      success: true,
      toolsList: toolsList.tools.map(t => t.name)
    };
    
  } catch (error) {
    return {
      method: 'MCP',
      content: '',
      contentLength: 0,
      latencyMs: Date.now() - startTime,
      estimatedTokens: 0,
      success: false,
      error: error.message
    };
  }
}

// ---------------------------------------------------------------------------
// Main comparison
// ---------------------------------------------------------------------------

async function runComparison() {
  console.log('='.repeat(70));
  console.log('Context7 MCP vs HTTP API Comparison');
  console.log('='.repeat(70));
  console.log();
  
  const results = {
    timestamp: new Date().toISOString(),
    library_id: 'uxlfoundation/onetbb',
    questions: TEST_QUESTIONS,
    comparisons: []
  };
  
  for (const question of TEST_QUESTIONS) {
    console.log(`\nTesting: "${question}"\n`);
    
    // Test HTTP API
    console.log('  [1/2] Fetching via HTTP API...');
    let httpResult;
    try {
      httpResult = await fetchViaHTTP('uxlfoundation/onetbb', question);
      console.log(`    ✓ Latency: ${httpResult.latencyMs}ms, Content: ${httpResult.contentLength} chars`);
    } catch (error) {
      console.log(`    ✗ Error: ${error.message}`);
      httpResult = { method: 'HTTP API', success: false, error: error.message };
    }
    
    // Test MCP
    console.log('  [2/2] Fetching via MCP...');
    let mcpResult;
    try {
      mcpResult = await fetchViaMCP('uxlfoundation/onetbb', question);
      if (mcpResult.success) {
        console.log(`    ✓ Latency: ${mcpResult.latencyMs}ms, Content: ${mcpResult.contentLength} chars`);
        if (mcpResult.toolsList) {
          console.log(`    Available tools: ${mcpResult.toolsList.join(', ')}`);
        }
      } else {
        console.log(`    ✗ Error: ${mcpResult.error}`);
      }
    } catch (error) {
      console.log(`    ✗ Error: ${error.message}`);
      mcpResult = { method: 'MCP', success: false, error: error.message };
    }
    
    results.comparisons.push({
      question,
      http: httpResult,
      mcp: mcpResult
    });
    
    // Rate limiting
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  
  // Print summary
  console.log('\n' + '='.repeat(70));
  console.log('SUMMARY');
  console.log('='.repeat(70));
  
  const httpSuccesses = results.comparisons.filter(c => c.http?.success).length;
  const mcpSuccesses = results.comparisons.filter(c => c.mcp?.success).length;
  
  console.log(`\nHTTP API: ${httpSuccesses}/${TEST_QUESTIONS.length} successful`);
  console.log(`MCP:      ${mcpSuccesses}/${TEST_QUESTIONS.length} successful`);
  
  if (httpSuccesses > 0) {
    const httpLatencies = results.comparisons
      .filter(c => c.http?.success)
      .map(c => c.http.latencyMs);
    const avgHttpLatency = httpLatencies.reduce((a, b) => a + b, 0) / httpLatencies.length;
    console.log(`\nHTTP API avg latency: ${avgHttpLatency.toFixed(0)}ms`);
  }
  
  if (mcpSuccesses > 0) {
    const mcpLatencies = results.comparisons
      .filter(c => c.mcp?.success)
      .map(c => c.mcp.latencyMs);
    const avgMcpLatency = mcpLatencies.reduce((a, b) => a + b, 0) / mcpLatencies.length;
    console.log(`MCP avg latency:      ${avgMcpLatency.toFixed(0)}ms`);
  }
  
  // Save full results
  const fs = require('fs');
  const outputFile = 'context7_comparison_results.json';
  fs.writeFileSync(outputFile, JSON.stringify(results, null, 2));
  console.log(`\n📊 Full results saved to: ${outputFile}`);
  
  return results;
}

// Run if called directly
if (require.main === module) {
  runComparison()
    .then(() => process.exit(0))
    .catch((error) => {
      console.error('Fatal error:', error);
      process.exit(1);
    });
}

module.exports = { runComparison, fetchViaHTTP, fetchViaMCP };
