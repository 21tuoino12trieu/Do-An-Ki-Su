# Sequence Diagram: BeeBankingApp Business Flow

```mermaid
sequenceDiagram
    participant User
    participant BeeBankingApp
    participant SessionManager
    participant IntentAnalyzer
    participant InformationCollector
    participant ApiService
    participant ResponseGenerator
    participant LLMService

    User->>BeeBankingApp: Send message
    BeeBankingApp->>BeeBankingApp: Initialize services
    BeeBankingApp->>SessionManager: Get session state
    BeeBankingApp->>IntentAnalyzer: Analyze intent and topic
    alt Content filtered
        IntentAnalyzer-->>BeeBankingApp: Filter result
        BeeBankingApp->>ResponseGenerator: Generate refusal response
        ResponseGenerator-->>BeeBankingApp: Refusal chunks
        BeeBankingApp-->>User: Send refusal
    else Cache hit
        BeeBankingApp->>ResponseGenerator: Generate cached response
        ResponseGenerator-->>BeeBankingApp: Cached response chunks
        BeeBankingApp-->>User: Send cached response
    else Continuation flow
        BeeBankingApp->>InformationCollector: Continue attribute collection
        InformationCollector-->>BeeBankingApp: Collection result
        alt Collection complete
            BeeBankingApp->>ApiService: Call API with attributes
            ApiService-->>BeeBankingApp: API response
            BeeBankingApp->>ResponseGenerator: Generate response with data
            ResponseGenerator-->>BeeBankingApp: Response chunks
            BeeBankingApp-->>User: Send response
        else
            BeeBankingApp->>ResponseGenerator: Generate collection question
            ResponseGenerator-->>BeeBankingApp: Question chunks
            BeeBankingApp-->>User: Send question
        end
    else Fresh analysis
        BeeBankingApp->>IntentAnalyzer: Analyze intent and topic
        IntentAnalyzer-->>BeeBankingApp: Intent and topic
        alt No attributes needed
            BeeBankingApp->>ApiService: Call API
            ApiService-->>BeeBankingApp: API response
            BeeBankingApp->>ResponseGenerator: Generate response
            ResponseGenerator-->>BeeBankingApp: Response chunks
            BeeBankingApp-->>User: Send response
        else
            BeeBankingApp->>InformationCollector: Collect required attributes
            InformationCollector-->>BeeBankingApp: Collection result
            alt Collection complete
                BeeBankingApp->>ApiService: Call API with attributes
                ApiService-->>BeeBankingApp: API response
                BeeBankingApp->>ResponseGenerator: Generate response with data
                ResponseGenerator-->>BeeBankingApp: Response chunks
                BeeBankingApp-->>User: Send response
            else
                BeeBankingApp->>ResponseGenerator: Generate collection question
                ResponseGenerator-->>BeeBankingApp: Question chunks
                BeeBankingApp-->>User: Send question
            end
        end
    end
```

## Flow Description

The BeeBankingApp processes user requests through a sophisticated orchestration of services:

1. **Initialization**: The app initializes core services including LLM, content filter, document service, and session manager.

2. **Preprocessing**: In parallel, it processes user profile and preloads session context.

3. **Content Filtering**: The message is checked for inappropriate content. If filtered, a refusal response is generated.

4. **Cache Check**: The system checks if the query has a cached response. If found, it returns the cached answer.

5. **Flow Decision**: Based on conversation context, the system determines if this is:
   - A continuation of an existing collection flow
   - A fresh analysis for a new request
   - An intent switch

6. **Attribute Collection**: For intents requiring additional information (like account number, date range), the system collects these attributes through conversation.

7. **API Integration**: Once all required attributes are collected, the app calls the appropriate API service.

8. **Response Generation**: The response generator creates a natural language response using the API data and returns it to the user.

The architecture uses a unified services pattern to eliminate code duplication and provide a consistent experience across all banking domains including deposits, cards, balance retrieval, and loan management.