import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import Qdrant
from qdrant_client import QdrantClient
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough, RunnableParallel
from langchain_core.output_parsers import StrOutputParser
from langchain.schema import Document

# --- 1. 환경 변수 및 설정 ---
load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


if not all([QDRANT_URL, QDRANT_API_KEY, OPENAI_API_KEY]):
    raise RuntimeError("QDRANT_URL, QDRANT_API_KEY, OPENAI_API_KEY 환경 변수를 설정해야 합니다.")

# --- 2. FastAPI 앱 및 Pydantic 모델 정의 ---
app = FastAPI(
    title="LearnSphere RAG API",
    description="Qdrant와 OpenAI를 사용하여 구축된 RAG 시스템과 상호 작용하는 API입니다.",
)

# API 요청 본문 모델
class RAGRequest(BaseModel):
    query: str
    collection: str = "react_docks_kr" # 기본값 설정

# API 응답 본문 모델
class RAGResponse(BaseModel):
    answer: str
    context: list[str]

# --- 3. RAG 파이프라인을 저장할 전역 변수 ---


# --- 4. RAG 파이프라인 초기화 (앱 시작 시 1회 실행) ---
# --- 4. RAG 파이프라인 초기화 (앱 시작 시 1회 실행) ---
# @app.on_event("startup")
# def initialize_rag_pipeline():
#     global rag_chain

#     # 임베딩 모델 및 LLM 초기화
#     embedding_model = OpenAIEmbeddings(model="text-embedding-ada-002")
#     llm = ChatOpenAI(model="gpt-4o", temperature=0)

    

#     # Qdrant Vector Store에 연결
#     qdrant_vector_store = Qdrant.from_existing_collection(
#         embedding=embedding_model,
#         collection_name=QDRANT_COLLECTION_NAME,
#         url=QDRANT_URL,
#         api_key=QDRANT_API_KEY,
#     )

#     # Retriever 생성 (유사 문서 검색기, 가장 유사한 문서 3개 반환)
#     retriever = qdrant_vector_store.as_retriever(search_kwargs={'k': 3})

#     # 프롬프트 템플릿 정의
#     prompt_template = """
#     당신은 주어진 컨텍스트를 바탕으로 사용자의 질문에 답변하는 AI 어시스턴트입니다.
#     컨텍스트에 답변에 대한 정보가 없으면, "죄송하지만 제공된 정보만으로는 답변할 수 없습니다."라고 답하세요.
#     답변은 항상 한국어로 작성해주세요.

#     컨텍스트:
#     {context}

#     질문:
#     {question}

#     답변:
#     """
#     prompt = ChatPromptTemplate.from_template(prompt_template)

#     # Document 객체 리스트를 하나의 문자열로 변환하는 헬퍼 함수
#     def format_docs(docs: list[Document]) -> str:
#         return "\n\n---\n\n".join([doc.page_content for doc in docs])

#     # LangChain Expression Language (LCEL)을 사용한 RAG 체인 구성
#     # RunnableParallel을 사용하여 retriever의 결과를 'answer'와 'context' 계산에 모두 활용
#     rag_chain_from_docs = (
#         RunnablePassthrough.assign(context=(lambda x: format_docs(x["context"]))) 
#         | prompt
#         | llm
#         | StrOutputParser()
#     )

#     rag_chain = RunnableParallel(
#         {"context": retriever, "question": RunnablePassthrough()}
#     ).assign(answer=rag_chain_from_docs)

#     print("RAG 파이프라인이 성공적으로 초기화되었습니다.")

# --- 5. API 엔드포인트 정의 ---
@app.get("/")
def read_root():
    return {"message": "RAG API에 오신 것을 환영합니다. /rag 엔드포인트를 사용하여 질문하세요."}

@app.post("/rag", response_model=RAGResponse)
async def perform_rag(request: RAGRequest):
    """
    사용자 질문에 대해 RAG 파이프라인을 수행하고 답변과 컨텍스트를 반환합니다.
    """
    # 임베딩 모델 및 LLM 초기화
    embedding_model = OpenAIEmbeddings(model="text-embedding-3-small", dimensions=768)
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # Qdrant Vector Store에 연결
    print(f"Connecting to Qdrant with URL: {QDRANT_URL}")
    print(f"Using collection: {request.collection}")
    client = QdrantClient(
        url=QDRANT_URL, 
        api_key=QDRANT_API_KEY,
    )
    qdrant_vector_store = Qdrant(
        client=client, 
        collection_name=request.collection, # 요청에서 받은 collection 사용
        embeddings=embedding_model,
    )

    # Retriever 생성 (유사 문서 검색기, 가장 유사한 문서 3개 반환)
    retriever = qdrant_vector_store.as_retriever(search_kwargs={'k': 3})

    # 프롬프트 템플릿 정의
    prompt_template = """
    당신은 주어진 컨텍스트를 바탕으로 사용자의 질문에 답변하는 AI 어시스턴트입니다.
    컨텍스트에 답변에 대한 정보가 없으면, "죄송하지만 제공된 정보만으로는 답변할 수 없습니다."라고 답하세요.
    답변은 항상 한국어로 작성해주세요.

    컨텍스트:
    {context}

    질문:
    {question}

    답변:
    """
    prompt = ChatPromptTemplate.from_template(prompt_template)

    # Document 객체 리스트를 하나의 문자열로 변환하는 헬퍼 함수
    def format_docs(docs: list[Document]) -> str:
        return "\n\n---\n\n".join([doc.page_content for doc in docs])

    # LangChain Expression Language (LCEL)을 사용한 RAG 체인 구성
    # RunnableParallel을 사용하여 retriever의 결과를 'answer'와 'context' 계산에 모두 활용
    rag_chain_from_docs = (
        RunnablePassthrough.assign(context=(lambda x: format_docs(x["context"]))) 
        | prompt
        | llm
        | StrOutputParser()
    )

    rag_chain = RunnableParallel(
        {"context": retriever, "question": RunnablePassthrough()}
    ).assign(answer=rag_chain_from_docs)

    try:
        # RAG 체인 실행
        result = rag_chain.invoke(request.query)

        # 결과에서 컨텍스트(Document 객체 리스트)와 답변 추출
        context_docs = result.get("context", [])
        answer = result.get("answer", "답변을 생성할 수 없습니다.")

        # Document 객체에서 page_content(원본 텍스트)만 추출하여 리스트로 만듦
        context_texts = [doc.page_content for doc in context_docs]

        return RAGResponse(answer=answer, context=context_texts)

    except Exception as e:
        print(f"RAG 체인 실행 중 에러 발생: {e}") # 디버깅을 위해 전체 에러 출력
        raise HTTPException(status_code=500, detail=f"RAG 처리 중 에러가 발생했습니다: {str(e)}")
