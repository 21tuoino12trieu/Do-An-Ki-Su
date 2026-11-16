# Beegen Chat

A powerful and flexible chat system with RAG (Retrieval-Augmented Generation) capabilities, built to handle sophisticated conversational AI interactions.

## 🌟 Features

- **Advanced RAG Pipeline**: Complete retrieval-augmented generation system with:
  - Multiple chunking strategies
  - Embedding generation
  - Reranking capabilities
  - Flexible retriever implementations
  - Vector database integration

- **Multiple LLM Support**: Modular architecture for various language models
  
- **Agent System**: Extensible agent framework for complex conversation handling

- **Configurable Architecture**: Highly customizable through configuration files

- **Logging System**: Comprehensive logging with multiple handlers

- **MongoDB Integration**: Built-in support for MongoDB operations

## 📁 Project Structure

```
beegen/
├── agents/          # Agent implementation and management
├── configs/         # Configuration management
├── llms/            # Language model integrations
├── logs/           # Logging system
│   └── handlers/   # Custom log handlers
├── prompts/        # Prompt templates and management
├── rag/            # RAG system components
│   ├── chunkings/  # Text chunking strategies
│   ├── embeddings/ # Embedding generation
│   ├── reranks/    # Reranking implementations
│   ├── retrievers/ # Retrieval methods
│   └── vectordb/   # Vector database interactions
├── tools/          # Utility tools
└── utils/          # Helper functions
    └── mongodb/    # MongoDB utilities
```

## 🚀 Getting Started

1. **Installation**
```bash
# Clone the repository
git clone [repository-url]

# Install dependencies
pip install -r requirements.txt
```

2. **Configuration**
- Copy `config/config.example.yaml` to `config/config.yaml`
- Update the configuration with your settings

3. **Running the System**
```bash
python entrypoints/openai/main.py
```

## 💻 Usage Examples

Check the `examples/` directory for implementation samples:
- Configuration examples
- Logging setup
- Vector database usage
- Utility functions

## 📝 Documentation

Detailed documentation is available in the `docs/` directory covering:
- System architecture
- Component interactions
- API references
- Configuration options

## 🛠️ Development

### Prerequisites
- Python 3.8+
- MongoDB
- Required environment variables (see `config/config.example.yaml`)

### Running Tests
```bash
pytest tests/
```

## Logging

The system uses a comprehensive logging system with:
- Multiple log handlers
- Configurable log levels
- Structured logging support
- Log rotation

Logs are stored in `system-logs/` directory.

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📜 License

[Add your license information here]

## 📞 Support

For support and questions:
- Open an issue
- Check the documentation
- [Add contact information if applicable]

---

Built with ❤️ by [Your Name/Organization]

