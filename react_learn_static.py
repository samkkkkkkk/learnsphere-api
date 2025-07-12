import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# .env 파일에서 환경 변수를 로드합니다.
load_dotenv()

# --- 1. 설정 ---
app = FastAPI()

# --- 2. CORS 설정 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 3. 요청 모델 정의 ---
class LevelRequest(BaseModel):
    level: str

# --- 4. 미리 생성된 학습 자료 데이터 ---
STATIC_LESSONS = {
    "초급": [
        {
            "title": "🚀 Your First Component 마스터하기 (초급)",
            "content": """## 🚀 Your First Component 마스터하기 (초급)

### 📘 Core Concepts
React 컴포넌트는 사용자 인터페이스를 구성하는 재사용 가능한 블록입니다. 웹 페이지를 구조화할 때 HTML 태그(<h1>, <li>, 등)를 사용하듯, React에서는 컴포넌트로 이러한 UI 요소들을 결합하고 관리할 수 있습니다. 컴포넌트는 일반적인 JavaScript 함수이며, 이름은 항상 대문자로 시작하고 JSX 문법을 통해 마크업을 반환합니다. React를 사용하면 동일한 컴포넌트를 여러 번 렌더링하여 애플리케이션의 일관성과 유지보수성을 향상시킬 수 있습니다.

### 💻 Code Examples
```javascript
// Profile 컴포넌트를 정의합니다.
export default function Profile() {
  return (
    <img
      src="https://i.imgur.com/MK3eW3As.jpg"
      alt="Katherine Johnson"
    />
  );
}

// Gallery 컴포넌트에서 Profile을 여러 번 사용합니다.
export default function Gallery() {
  return (
    <section>
      <h1>Amazing scientists</h1>
      <Profile />
      <Profile />
      <Profile />
    </section>
  );
}
```

### 📝 Quiz
1. **문제**: React 컴포넌트의 이름은 어떻게 시작해야 하나요?
   **정답**: 컴포넌트의 이름은 항상 대문자로 시작해야 합니다. 이는 React가 컴포넌트를 일반 HTML 태그와 구분하기 위해 필요한 규칙입니다.

2. **문제**: JSX는 무엇인가요?
   **정답**: JSX는 JavaScript 파일 내에서 마크업을 작성하는 문법입니다. 일반적인 HTML과 비슷하지만, JavaScript 코드 안에서 사용되며 컴포넌트를 정의할 때 주로 사용됩니다.

3. **문제**: Profile 컴포넌트를 여러 번 사용함으로써 얻는 이점은 무엇인가요?
   **정답**: 컴포넌트를 재사용함으로써 코드의 일관성을 높이고, 유지보수를 쉽게 할 수 있습니다. 같은 기능을 여러 곳에서 다시 작성할 필요 없이, 단지 컴포넌트를 호출하기만 하면 됩니다."""
        },
        {
            "title": "📦 컴포넌트 가져오기 및 내보내기 마스터하기 (초급)",
            "content": """## 📦 컴포넌트 가져오기 및 내보내기 마스터하기 (초급)

### 📘 Core Concepts
컴포넌트를 가져오고 내보내는 것은 React의 기본입니다. 이 과정은 컴포넌트를 다른 파일에서 사용할 수 있게 해줍니다. React에서는 두 가지 방식으로 컴포넌트를 내보낼 수 있습니다: default export와 named export.

Default Export: 한 파일에서 오직 하나의 컴포넌트를 기본으로 내보낼 수 있습니다. 이 경우, 다른 파일에서 가져올 때는 중괄호를 사용할 필요가 없습니다.

Named Export: 하나의 파일에서 여러 개의 컴포넌트를 내보낼 수 있습니다. 이 경우, 가져올 때는 반드시 중괄호를 사용해야 하며, 가져올 컴포넌트의 이름을 정확히 일치시켜야 합니다.

이러한 방식들은 컴포넌트의 재사용성을 높이고, 코드의 가독성을 향상시킵니다. 코드의 분리와 모듈화를 통해 더 나은 유지보수를 지원합니다.

### 💻 Code Examples
```javascript
// Profile.js
export function Profile() {
  return (
    <img
      src="https://i.imgur.com/QIrZWGIs.jpg"
      alt="Alan L. Hart"
    />
  );
}

// Gallery.js
import { Profile } from './Profile.js';

export default function Gallery() {
  return (
    <section>
      <h1>Amazing scientists</h1>
      <Profile />
      <Profile />
      <Profile />
    </section>
  );
}

// App.js
import Gallery from './Gallery.js';

export default function App() {
  return (
    <Gallery />
  );
}
```

### 📝 Quiz
1. **문제**: 한 파일에서 기본적으로 내보낼 수 있는 컴포넌트의 수는 몇 개인가요?
   **정답**: 한 파일에서 오직 하나의 default export만 존재할 수 있습니다.

2. **문제**: named export 방식을 사용할 때 컴포넌트를 가져오기 위해 사용하는 문법은 무엇인가요?
   **정답**: 중괄호를 사용해야 하며, 가져올 컴포넌트의 이름을 일치시켜야 합니다. 예: import { Profile } from './Profile.js';

3. **문제**: 컴포넌트를 여러 파일로 나누는 이유는 무엇인가요?
   **정답**: 재사용성을 높이고, 코드의 가독성을 향상시키며, 유지보수를 쉽게 하기 위해서입니다."""
        },
        {
            "title": "🎯 Props를 통한 데이터 전달 마스터하기 (초급)",
            "content": """## 🎯 Props를 통한 데이터 전달 마스터하기 (초급)

### 📘 Core Concepts
Props는 React에서 부모 컴포넌트가 자식 컴포넌트에게 데이터를 전달하는 방법입니다. Props는 읽기 전용이며, 컴포넌트가 props를 받아서 렌더링할 수 있지만, 받은 props를 직접 수정할 수는 없습니다. Props는 객체 형태로 전달되며, 구조 분해 할당을 통해 개별 속성에 접근할 수 있습니다.

Props를 사용하면 컴포넌트를 더 유연하고 재사용 가능하게 만들 수 있습니다. 같은 컴포넌트를 다른 데이터로 렌더링할 수 있어서, 다양한 상황에서 활용할 수 있습니다.

### 💻 Code Examples
```javascript
// Avatar 컴포넌트 - props를 받아서 렌더링
function Avatar({ person, size }) {
  return (
    <img
      className="avatar"
      src={person.imageId}
      alt={person.name}
      width={size}
      height={size}
    />
  );
}

// Profile 컴포넌트 - Avatar에 props 전달
export default function Profile() {
  return (
    <div>
      <Avatar
        person={{ name: 'Lin Lanying', imageId: '1bX5QH6' }}
        size={100}
      />
      <Avatar
        person={{ name: 'Gregorio Y. Zara', imageId: 'YfeOqp2' }}
        size={80}
      />
    </div>
  );
}
```

### 📝 Quiz
1. **문제**: 컴포넌트에 props를 전달하는 기본 방법은 무엇인가요?
   **정답**: JSX에 HTML 어트리뷰트를 추가하듯이 props를 추가하는 것입니다.

2. **문제**: props는 어떻게 읽는가요?
   **정답**: 구조 분해 할당을 사용하여 `function ComponentName({ prop1, prop2 })`와 같은 형태로 읽습니다.

3. **문제**: props에 기본값을 설정하는 방법은 무엇인가요?
   **정답**: 구조 분해 할당 시 변수 뒤에 `=` 연산자를 사용하여 기본값을 지정할 수 있습니다. 예: `function Component({ prop = defaultValue })`."""
        }
    ],
    "중급": [
        {
            "title": "🔄 State와 이벤트 핸들링 마스터하기 (중급)",
            "content": """## 🔄 State와 이벤트 핸들링 마스터하기 (중급)

### 📘 Core Concepts
State는 React 컴포넌트의 메모리입니다. State를 사용하면 컴포넌트가 시간이 지남에 따라 정보를 기억하고 변경할 수 있습니다. useState 훅을 사용하여 state를 관리하며, state가 변경되면 컴포넌트가 다시 렌더링됩니다.

이벤트 핸들링은 사용자의 상호작용에 반응하는 방법입니다. React에서는 camelCase로 이벤트 핸들러를 작성하며, 함수를 직접 전달하거나 인라인 함수를 사용할 수 있습니다.

### 💻 Code Examples
```javascript
import { useState } from 'react';

export default function Counter() {
  const [count, setCount] = useState(0);

  function handleClick() {
    setCount(count + 1);
  }

  return (
    <button onClick={handleClick}>
      You clicked me {count} times
    </button>
  );
}

// 폼 이벤트 핸들링
function MyForm() {
  const [name, setName] = useState('');

  function handleSubmit(e) {
    e.preventDefault();
    alert('Hello, ' + name);
  }

  return (
    <form onSubmit={handleSubmit}>
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <button type="submit">Submit</button>
    </form>
  );
}
```

### 📝 Quiz
1. **문제**: useState 훅의 기본 문법은 무엇인가요?
   **정답**: `const [state, setState] = useState(initialValue)` 형태로 사용합니다. state는 현재 값, setState는 state를 업데이트하는 함수입니다.

2. **문제**: 이벤트 핸들러에서 e.preventDefault()를 사용하는 이유는 무엇인가요?
   **정답**: 기본 브라우저 동작을 막기 위해서입니다. 예를 들어 폼 제출 시 페이지가 새로고침되는 것을 방지할 수 있습니다.

3. **문제**: State 업데이트 시 주의해야 할 점은 무엇인가요?
   **정답**: State는 불변성을 유지해야 하며, 직접 수정하지 말고 setter 함수를 사용해야 합니다."""
        },
        {
            "title": "🎨 조건부 렌더링과 리스트 마스터하기 (중급)",
            "content": """## 🎨 조건부 렌더링과 리스트 마스터하기 (중급)

### 📘 Core Concepts
조건부 렌더링은 특정 조건에 따라 다른 UI를 보여주는 방법입니다. JavaScript의 조건문(if, 삼항 연산자)을 사용하여 조건부 렌더링을 구현할 수 있습니다.

리스트 렌더링은 배열의 데이터를 기반으로 여러 컴포넌트를 생성하는 방법입니다. map 함수를 사용하여 배열의 각 요소를 컴포넌트로 변환할 수 있으며, key prop을 사용하여 React가 각 요소를 식별할 수 있도록 해야 합니다.

### 💻 Code Examples
```javascript
// 조건부 렌더링
function Greeting({ isLoggedIn }) {
  if (isLoggedIn) {
    return <h1>Welcome back!</h1>;
  }
  return <h1>Please sign up.</h1>;
}

// 삼항 연산자를 사용한 조건부 렌더링
function Greeting({ isLoggedIn }) {
  return (
    <h1>
      {isLoggedIn ? 'Welcome back!' : 'Please sign up.'}
    </h1>
  );
}

// 리스트 렌더링
function NumberList({ numbers }) {
  const listItems = numbers.map((number) =>
    <li key={number.toString()}>
      {number}
    </li>
  );
  return (
    <ul>{listItems}</ul>
  );
}

// 사용 예시
const numbers = [1, 2, 3, 4, 5];
<NumberList numbers={numbers} />
```

### 📝 Quiz
1. **문제**: 조건부 렌더링에서 key prop이 중요한 이유는 무엇인가요?
   **정답**: React가 각 요소를 고유하게 식별하여 효율적으로 업데이트할 수 있도록 하기 때문입니다.

2. **문제**: 리스트 렌더링 시 배열의 인덱스를 key로 사용하는 것이 좋지 않은 이유는 무엇인가요?
   **정답**: 배열의 순서가 변경되거나 요소가 추가/삭제될 때 React가 올바르게 업데이트하지 못할 수 있기 때문입니다.

3. **문제**: 조건부 렌더링에서 && 연산자를 사용할 때 주의해야 할 점은 무엇인가요?
   **정답**: 0과 같은 falsy 값이 렌더링될 수 있으므로, 명시적으로 boolean 값을 반환하도록 주의해야 합니다."""
        }
    ],
    "고급": [
        {
            "title": "🧠 Custom Hooks와 상태 관리 마스터하기 (고급)",
            "content": """## 🧠 Custom Hooks와 상태 관리 마스터하기 (고급)

### 📘 Core Concepts
Custom Hooks는 React의 로직을 재사용 가능한 함수로 추출하는 방법입니다. "use"로 시작하는 함수를 만들어서 다른 컴포넌트에서 사용할 수 있습니다. Custom Hooks는 상태 관리, 이벤트 핸들링, API 호출 등의 로직을 캡슐화할 수 있습니다.

상태 관리에서는 복잡한 상태를 여러 개의 단순한 상태로 분리하거나, useReducer를 사용하여 복잡한 상태 로직을 관리할 수 있습니다.

### 💻 Code Examples
```javascript
// Custom Hook 예시
import { useState, useEffect } from 'react';

function useCounter(initialValue = 0) {
  const [count, setCount] = useState(initialValue);
  
  const increment = () => setCount(count + 1);
  const decrement = () => setCount(count - 1);
  const reset = () => setCount(initialValue);
  
  return { count, increment, decrement, reset };
}

// Custom Hook 사용
function Counter() {
  const { count, increment, decrement, reset } = useCounter(0);
  
  return (
    <div>
      <p>Count: {count}</p>
      <button onClick={increment}>+</button>
      <button onClick={decrement}>-</button>
      <button onClick={reset}>Reset</button>
    </div>
  );
}

// useReducer 예시
import { useReducer } from 'react';

function reducer(state, action) {
  switch (action.type) {
    case 'increment':
      return { count: state.count + 1 };
    case 'decrement':
      return { count: state.count - 1 };
    default:
      throw new Error();
  }
}

function Counter() {
  const [state, dispatch] = useReducer(reducer, { count: 0 });
  
  return (
    <div>
      Count: {state.count}
      <button onClick={() => dispatch({ type: 'increment' })}>+</button>
      <button onClick={() => dispatch({ type: 'decrement' })}>-</button>
    </div>
  );
}
```

### 📝 Quiz
1. **문제**: Custom Hook의 이름은 어떤 규칙을 따라야 하나요?
   **정답**: "use"로 시작해야 합니다. 이는 React가 Hook임을 인식하고 Hook의 규칙을 적용하기 위함입니다.

2. **문제**: useReducer를 사용하는 적절한 상황은 언제인가요?
   **정답**: 복잡한 상태 로직이 있거나, 다음 상태가 이전 상태에 의존하는 경우, 또는 여러 하위 값이 포함된 상태 객체를 관리할 때 사용합니다.

3. **문제**: Custom Hook에서 다른 Hook을 호출할 수 있나요?
   **정답**: 네, 가능합니다. Custom Hook 내부에서 useState, useEffect 등 다른 Hook들을 사용할 수 있습니다."""
        },
        {
            "title": "⚡ 성능 최적화와 메모이제이션 마스터하기 (고급)",
            "content": """## ⚡ 성능 최적화와 메모이제이션 마스터하기 (고급)

### 📘 Core Concepts
React의 성능 최적화는 불필요한 리렌더링을 방지하는 것이 핵심입니다. React.memo, useMemo, useCallback을 사용하여 컴포넌트와 함수를 메모이제이션할 수 있습니다.

React.memo는 props가 변경되지 않으면 컴포넌트를 리렌더링하지 않습니다. useMemo는 계산 비용이 높은 값을 메모이제이션하고, useCallback은 함수를 메모이제이션하여 자식 컴포넌트의 불필요한 리렌더링을 방지합니다.

### 💻 Code Examples
```javascript
import React, { useMemo, useCallback, useState } from 'react';

// React.memo를 사용한 컴포넌트 최적화
const ExpensiveComponent = React.memo(({ value }) => {
  console.log('ExpensiveComponent rendered');
  return <div>Value: {value}</div>;
});

// useMemo를 사용한 계산 결과 메모이제이션
function Calculator({ numbers }) {
  const sum = useMemo(() => {
    console.log('Calculating sum...');
    return numbers.reduce((acc, num) => acc + num, 0);
  }, [numbers]);

  return <div>Sum: {sum}</div>;
}

// useCallback을 사용한 함수 메모이제이션
function ParentComponent() {
  const [count, setCount] = useState(0);
  
  const handleClick = useCallback(() => {
    console.log('Button clicked');
  }, []); // 의존성 배열이 비어있으므로 함수는 한 번만 생성됨

  return (
    <div>
      <button onClick={() => setCount(count + 1)}>
        Count: {count}
      </button>
      <ExpensiveComponent value={count} onClick={handleClick} />
    </div>
  );
}

// 가상화를 사용한 대용량 리스트 최적화
import { FixedSizeList as List } from 'react-window';

function VirtualizedList({ items }) {
  const Row = ({ index, style }) => (
    <div style={style}>
      Row {index}: {items[index]}
    </div>
  );

  return (
    <List
      height={400}
      itemCount={items.length}
      itemSize={35}
    >
      {Row}
    </List>
  );
}
```

### 📝 Quiz
1. **문제**: useMemo와 useCallback의 차이점은 무엇인가요?
   **정답**: useMemo는 계산된 값을 메모이제이션하고, useCallback은 함수 자체를 메모이제이션합니다.

2. **문제**: React.memo를 사용할 때 주의해야 할 점은 무엇인가요?
   **정답**: 객체나 함수를 props로 전달할 때 매번 새로운 참조가 생성되지 않도록 주의해야 합니다.

3. **문제**: 성능 최적화를 과도하게 적용하면 어떤 문제가 발생할 수 있나요?
   **정답**: 코드가 복잡해지고, 메모리 사용량이 증가하며, 실제로는 성능 향상이 미미할 수 있습니다."""
        }
    ]
}

# --- 5. API 엔드포인트 ---
@app.post("/api/generate-topic-lessons")
def generate_topic_lessons_endpoint(request: LevelRequest):
    """
    미리 생성된 정적 학습 자료를 반환합니다.
    """
    try:
        lessons = STATIC_LESSONS.get(request.level, [])
        if not lessons:
            raise HTTPException(
                status_code=400, 
                detail=f"'{request.level}' 레벨에 해당하는 학습 자료가 없습니다."
            )
        
        print(f"--- '{request.level}' 레벨의 정적 학습 자료 {len(lessons)}개 반환 ---")
        return {"lessons": lessons}
        
    except Exception as e:
        print(f"서버 오류 발생: {e}")
        raise HTTPException(status_code=500, detail="서버 내부 오류가 발생했습니다.")

@app.get("/")
def read_root():
    return {"message": "React 정적 학습 자료 API 서버가 실행 중입니다."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 