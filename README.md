<div align="center">

   <h1>🎞️ Virex 블랙박스 영상 복구 및 분석 도구</h1> 

   <img width=100% alt="Virex 배너" src="https://github.com/user-attachments/assets/10dfd0c3-3aab-40a4-91c8-d0b8187399fc" />

   <p>
     손상된 영상부터 슬랙 영상까지 다양한 포맷(E01, 001, AVI, MP4, JDR)에서 복원하고 분석할 수 있는 데스크탑 애플리케이션입니다.<br />
     볼륨/파일 단위 슬랙 영역까지 분석하여 복원률을 높이며, 복원된 영상은 리스트 형태로 정리되어 직접 확인하고 원하는 경로에 저장할 수 있습니다.
   </p>
</div>

<br />

## 목차
1. [시작하기](#시작하기)
2. [설치 및 실행 방법](#설치-및-실행-방법)
3. [주요 기능](#주요-기능)
4. [메뉴별 기능 안내](#메뉴별-기능-안내)
   
<br />

## 시작하기
Virex를 통해 `.e01`, `.001`, `.avi`, `.mp4`, `.jdr` 등 다양한 블랙박스 영상을 복원할 수 있습니다. <br />
입력한 파일 종류에 따라 분석 및 복원 방식이 달라지며, 전체 흐름은 다음과 같습니다.

<div align="center">
  <img src="https://github.com/user-attachments/assets/d60048db-0f7c-4079-829a-3c131e5b7034" alt="전체흐름" />
</div>

1. 복원할 파일(E01/001, AVI, MP4, JDR)을 선택합니다.  
2. Virex가 자동으로 분석을 시작하고, 영상과 슬랙 영역 데이터를 복원합니다.  
3. 복원된 영상 목록과 분석 결과를 확인한 후 원하는 경로로 다운로드합니다.

<br />

## 설치 및 실행 방법

### 릴리즈 버전 설치
1. [Releases 페이지](https://github.com/Team-JUST/Virex/releases)에서 최신 버전(`v2.0.1`)의 설치 파일(`Virex-Setup-2.0.1.exe`)을 다운로드합니다.  
2. 다운로드한 `.exe` 파일을 실행하면 설치 마법사가 시작됩니다.  
3. 설치 경로를 선택한 후 안내에 따라 설치를 완료하세요.  
4. 바탕화면 또는 시작 메뉴에서 **Virex**를 실행할 수 있습니다.  

> Virex는 Windows 환경 전용입니다. (Windows 10 이상 권장)

<br />

## 주요 기능
- **다양한 포맷 지원**: E01/001 디스크 이미지, AVI, MP4, JDR 파일 복원 기능
- **자동 분석 및 복원**: 파일 선택 시 영상 및 슬랙 영역 데이터 자동 분석/복원
- **슬랙 영역 복원**: 볼륨/파일 단위의 슬랙 프레임까지 추출하여 복원률 향상
- **복원 결과 제공**: 영상별 복원률, 손상 사유, 메타데이터 확인 가능
- **다운로드 기능**: 원본/슬랙 영상 및 프레임 이미지(ZIP 포함) 사용자 지정 경로로 저장
- **UI 편의 기능**: 다크/라이트 모드 전환, 임시 캐시 파일 삭제, 알림 on/off 설정 지원

<br />

## 메뉴별 기능 안내

### Home
<img width="1000" height="735" alt="image" src="https://github.com/user-attachments/assets/3ac84dc7-b399-4f87-bf54-a55db9d439b9" />

- 로컬 드라이브 자동 인식  
- 드라이브 내 폴더 탐색 가능  
- `.e01`, `.001`, `.avi`, `.mp4`, `.jdr` 파일 선택 후 복원 시작 가능  

<br />

### Recovery
<div align="center">
  <img src="https://github.com/user-attachments/assets/e6f18267-631f-4689-b6a5-cc9a6388b19a" alt="복원리스트" />
</div>

- 복원 시작을 위한 파일 탐색기 사용  
- 영상 추출 + 슬랙 영상 복원 + 분석 동시 진행  
- 복원 완료 시 영상 리스트 확인 가능
- 영상 리스트에 태그 표시
  - `손상` 태그: 손상된 영상인 경우 표시
  - `복원 완료` 태그: 손상되었으나 정상적으로 복원된 경우 표시
  - `슬랙` 태그: 슬랙 복원본이 있는 경우 표시
- 영상 리스트 클릭 시 상세 정보 확인 가능
  - 메타데이터, 복원률, 손상 사유 등을 확인
- `슬랙` 태그 클릭 시, 해당 영상의 **슬랙 복원본** 확인 가능
  - 슬랙 복원본에 오디오가 포함된 경우 **오디오 뱃지**가 함께 표시
  - 오디오 뱃지가 보이면 해당 영상은 **슬랙 오디오**까지 추출된 상태

<br />

#### 포맷별 추가 기능
- **AVI**
  ![Recovery_avi](https://github.com/user-attachments/assets/56a824e6-0b1e-4cd4-9ed2-0bd19db53176)
  - 영상 상세 페이지에서 `Front`, `Rear`, `Side` 등 **채널 뱃지**가 표시됩니다.  
  - 각 채널별로 분리된 영상을 선택하여 확인 가능하며, 채널별 복원률도 별도로 확인할 수 있습니다.  

- **JDR**
  ![Recovery_jdr](https://github.com/user-attachments/assets/c598ee1f-0924-451d-b006-2d4ae318dcf8)
  - 독자 포맷 특성상 **메타데이터 추출이 어렵기 때문에 분석 탭은 제공되지 않습니다.**  
  - 대신 복원된 영상을 직접 확인할 수 있으며, 슬랙 복원본이 존재하면 `슬랙` 태그가 표시됩니다.
 
> **MP4**  
> 위에서 설명한 기능이 MP4 파일의 기본 동작 방식입니다.  

<br />

#### 다운로드 기능
<div align="center">
  <img width=800 src="https://github.com/user-attachments/assets/0858f2e3-3a2a-412c-a23b-755c8e9051bb" alt="다운로드" />  
</div>

- 복원 영상 선택 다운로드 가능  
  - 예 선택 시 → 원본 + 슬랙 영상 + 프레임 이미지(`.zip`) 파일 다운로드  
  - 아니오 선택 시 → 원본 + 슬랙 영상만 다운로드
  - 슬랙 오디오가 존재하는 경우 → 오디오 파일도 함께 다운로드됨  
- 원하는 폴더로 경로 지정 가능

<br />

### Setting
<div align="center">
  <img width="800" alt="image" src="https://github.com/user-attachments/assets/41b1560b-86eb-4678-80c7-8fc27b0b420c" />
</div>

- 다크모드 / 라이트모드 전환  
- 캐시 파일 삭제 (`Virex_xxx` 등 temp 파일 제거)  
- 알림 기능 켜기/끄기

<br />

### Information
<div align="center">
  <img width="800" alt="image" src="https://github.com/user-attachments/assets/6e8beae4-c738-4130-890c-255c7156386a" />
</div>

- Virex 버전 및 개발자 정보, 기술 스택 정보 제공
