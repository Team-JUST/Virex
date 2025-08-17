<div align="center">

   <h1>🎞️ Retato 블랙박스 영상 복구 및 분석 도구</h1> 

   <img width=100% alt="Retato 배너" src="https://github.com/user-attachments/assets/ba3f57fe-80f8-4e28-9c62-fac9325d23e5" />

   <p>
     E01 디스크 이미지에서 영상과 슬랙 공간의 잔여 영상까지 복원할 수 있는 데스크탑 애플리케이션입니다.<br />
     복원된 영상은 리스트 형태로 정리되어 있으며, 각 영상을 직접 확인하고 원하는 경로에 저장할 수 있습니다.
   </p>
</div>

<br />

## 목차
1. [시작하기](#시작하기)
2. [주요 기능](#주요-기능)
3. [메뉴별 기능 안내](#메뉴별-기능-안내)
   
<br />

## 시작하기
Retato를 통해 `.e01` 디스크 이미지에서 영상을 복원하는 전체 흐름은 다음과 같습니다.

<div align="center">
  <img src="https://github.com/user-attachments/assets/8c81dcc7-147a-4b81-b767-e95d0d007dec" alt="전체흐름" />
</div>

1. `.e01` 파일을 선택합니다.  
2. Retato가 자동으로 분석을 시작하고, 영상 및 슬랙 공간에서 데이터를 복원합니다.  
3. 복원된 영상 목록을 미리보기 및 분석 결과와 함께 확인한 후 다운로드합니다.

<br />

## 주요 기능
- **E01 파일 선택 및 분석 자동화**
- **영상 및 슬랙 영상 추출**
- **복원 영상별 분석 결과 제공**
- **사용자 지정 경로로 영상/프레임 다운로드**
- **다크/라이트 모드 전환 지원**
- **임시 캐시 파일 삭제 기능**
- **알림 기능 on/off 설정**

<br />

## 메뉴별 기능 안내

### Home
- 로컬 드라이브 자동 인식  
- 드라이브 내 폴더 탐색 가능  
- `.e01` 파일 선택 후 복원 시작 가능

<br />

### Recovery
<div align="center">
  <img src="https://github.com/user-attachments/assets/1c06973e-a98d-4248-b08f-227fa4f86696" alt="복원리스트" />
</div>

- 복원 시작을 위한 파일 탐색기 사용  
- 영상 추출 + 슬랙 영상 복원 + 분석 동시 진행  
- 복원 완료 시 영상 리스트 확인 가능
- 슬랙이 있는 영상은 `슬랙` 태그로 표시 
- 영상 리스트 클릭 시 상세 정보 확인
  - 손상 파일의 경우 손상 사유 확인 가능
- `슬랙` 태그 클릭 시, 해당 영상의 슬랙 복원본 확인

<br />

#### 다운로드 기능
<div align="center">
  <img src="https://github.com/user-attachments/assets/c039328a-c3a9-4013-bf05-26f090f6c785" alt="다운로드" />
</div>

- 복원 영상 일괄 다운로드 가능  
  - 예 선택 시 → 원본 + 슬랙 영상 + 프레임 이미지(`.zip`) 파일 다운로드  
  - 아니오 선택 시 → 원본 + 슬랙 영상만 다운로드  
- 원하는 폴더로 경로 지정 가능


<br />

### Setting
<div align="center">
  <img width="800" alt="image" src="https://github.com/user-attachments/assets/eaebc74f-1ec3-410d-8482-6f8482697f4f" />
</div>

- 다크모드 / 라이트모드 전환  
- 캐시 파일 삭제 (`retato_xxx` 등 temp 파일 제거)  
- 알림 기능 켜기/끄기

<br />

### Information
<div align="center">
  <img width="800" alt="image" src="https://github.com/user-attachments/assets/13510862-9a18-464e-830d-1565f9aea949" />
</div>

- Retato 버전 및 개발자 정보, 기술 스택 정보 제공