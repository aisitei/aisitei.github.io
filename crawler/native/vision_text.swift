// Local Chinese text recognition. Never describes or generates image content.
import Foundation
import Vision

struct RecognizedLine: Codable {
    let text: String
    let confidence: Float
}

do {
    guard CommandLine.arguments.count == 2 else {
        throw NSError(domain: "OCR", code: 1, userInfo: [NSLocalizedDescriptionKey: "Expected one image path"])
    }
    let data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["zh-Hans", "en-US"]
    request.usesLanguageCorrection = true
    try VNImageRequestHandler(data: data, options: [:]).perform([request])
    let lines = (request.results ?? []).compactMap { observation -> RecognizedLine? in
        guard let candidate = observation.topCandidates(1).first else { return nil }
        return RecognizedLine(text: candidate.string, confidence: candidate.confidence)
    }
    FileHandle.standardOutput.write(try JSONEncoder().encode(lines))
} catch {
    FileHandle.standardError.write(Data("OCR: \(error.localizedDescription)\n".utf8))
    exit(1)
}
