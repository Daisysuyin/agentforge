import { gql } from "@apollo/client";

export const TOOLS_QUERY = gql`
  query Tools {
    tools {
      name
      description
      schemaJson
    }
  }
`;

export const AGENTS_QUERY = gql`
  query Agents {
    agents {
      id
      name
      description
      role
      systemPrompt
      toolNames
      guardrailsJson
      createdAt
      updatedAt
    }
  }
`;

export const TRACES_QUERY = gql`
  query Traces($agentId: String, $limit: Int) {
    traces(agentId: $agentId, limit: $limit) {
      id
      agentId
      userInput
      finalOutput
      status
      error
      durationMs
      tokensIn
      tokensOut
      createdAt
      toolCalls {
        id
        sequence
        toolName
        argumentsJson
        resultJson
        error
        durationMs
      }
    }
  }
`;

export const CREATE_AGENT = gql`
  mutation CreateAgent($input: CreateAgentInput!) {
    createAgent(input: $input) {
      id
      name
      role
      systemPrompt
      toolNames
      guardrailsJson
    }
  }
`;

export const UPDATE_AGENT = gql`
  mutation UpdateAgent($input: UpdateAgentInput!) {
    updateAgent(input: $input) {
      id
      name
      role
      systemPrompt
      toolNames
      guardrailsJson
    }
  }
`;

export const DELETE_AGENT = gql`
  mutation DeleteAgent($id: String!) {
    deleteAgent(id: $id)
  }
`;

export const RUN_EVAL = gql`
  mutation RunEvalSuite($fixturePath: String, $useJudge: Boolean) {
    runEvalSuite(fixturePath: $fixturePath, useJudge: $useJudge) {
      n
      toolAccuracy
      textAccuracy
      avgJudgeScore
      p50LatencyMs
      p95LatencyMs
      errorRate
      cases {
        caseId
        userInput
        finalText
        toolCallsMade
        expectedTools
        toolsMatch
        textMatch
        judgeScore
        error
        durationMs
      }
    }
  }
`;
